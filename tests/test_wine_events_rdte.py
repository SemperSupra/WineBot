"""Isolated three-audience read-only Wine event API qualification.

All sessions/tokens are synthetic. No real app, hardware or network service.
"""
import json
import os
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.core.wine_events_rdte import registry
from api.routers.wine_events_rdte import router
from rdte.wine11.event_bridge import EventBridge

SESSION = "session-synthetic-1"
ROOT = "/tmp/synthetic/" + SESSION
TOKEN = "synthetic-rdte-test-token"
URL = "/sessions/" + SESSION + "/observations/wine-events"


def event(kind, seq):
    return json.dumps({"schema": "winebot.wine.event.v1", "kind": kind, "sequence": seq})


class SessionEventApiTests(TestCase):
    def setUp(self):
        registry.clear()
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)
        self.env = patch.dict(os.environ, {
            "API_TOKEN": TOKEN,
            "WINEBOT_WINE_EVENTS_RDTE_ENABLED": "1",
        })
        self.env.start()
        self.dir_patch = patch("api.routers.wine_events_rdte.read_session_dir", return_value=ROOT)
        self.dir_patch.start()
        self.state_patch = patch(
            "api.routers.wine_events_rdte.broker.get_state",
            return_value=SimpleNamespace(session_id=SESSION),
        )
        self.state_patch.start()

    def tearDown(self):
        registry.clear()
        self.state_patch.stop()
        self.dir_patch.stop()
        self.env.stop()
        self.client.close()

    def get(self, url=URL, token=TOKEN, **kwargs):
        headers = {"X-API-Key": token} if token is not None else {}
        return self.client.get(url, headers=headers, **kwargs)

    def attach(self):
        b = EventBridge()
        self.assertTrue(b.ingest(event("ready", 0)))
        self.assertTrue(b.ingest(event("show", 1)))
        self.assertTrue(b.ingest(event("location", 2)))
        registry.attach_internal(SESSION, b)
        return b

    def test_read_only_but_unavailable_without_source(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "schema": "winebot.wine.event.v1",
            "state": "unavailable", "events": [], "next_cursor": 0,
        })

    def test_authorized_human_automation_agent_share_one_snapshot(self):
        self.attach()
        for audience in ("human", "automation", "agent"):
            with self.subTest(audience=audience):
                result = self.get(params={"limit": 1}).json()
                self.assertEqual(result["state"], "ready")
                self.assertEqual(result["events"], [{"sequence": 1, "kind": "show"}])
                self.assertEqual(result["next_cursor"], 1)
                second = self.get(params={"after": 1}).json()
                self.assertEqual(second["events"], [{"sequence": 2, "kind": "location"}])

    def test_unknown_session_cannot_read_other_stream(self):
        self.attach()
        url = "/sessions/session-other/observations/wine-events"
        self.assertEqual(self.get(url).status_code, 404)
        self.assertEqual(self.get().json()["state"], "ready")

    def test_missing_wrong_and_empty_token_fail_closed(self):
        self.attach()
        self.assertEqual(self.get(token=None).status_code, 401)
        self.assertEqual(self.get(token="incorrect").status_code, 401)
        with patch.dict(os.environ, {"API_TOKEN": ""}):
            with patch("api.routers.wine_events_rdte.config.API_TOKEN", None):
                self.assertEqual(self.get().status_code, 503)

    def test_feature_disabled_cannot_reach_observer(self):
        self.attach()
        with patch.dict(os.environ, {"WINEBOT_WINE_EVENTS_RDTE_ENABLED": "0"}):
            self.assertEqual(self.get().status_code, 404)

    def test_stale_broker_session_rejected(self):
        self.attach()
        with patch(
            "api.routers.wine_events_rdte.broker.get_state",
            return_value=SimpleNamespace(session_id="old-session"),
        ):
            self.assertEqual(self.get().status_code, 409)

    def test_session_handover_erases_previous_observations(self):
        original = self.attach()
        with patch("api.routers.wine_events_rdte.read_session_dir",
                   return_value="/tmp/synthetic/session-next"):
            self.assertEqual(self.get().status_code, 404)
        self.assertEqual(original.observe()["state"], "unqualified")
        self.assertEqual(registry.observe(SESSION)["state"], "unavailable")

    def test_no_active_session_and_malformed_cursor_fail(self):
        with patch("api.routers.wine_events_rdte.read_session_dir", return_value=None):
            self.assertEqual(self.get().status_code, 409)
        self.assertEqual(self.get(params={"limit": 0}).status_code, 422)
        self.assertEqual(self.get(params={"after": -1}).status_code, 422)

    def test_capabilities_disclaim_uia_and_cv(self):
        capability_url = URL + "/capabilities"
        unavailable = self.get(capability_url).json()
        self.assertEqual(unavailable["collector"], "unavailable")
        self.assertEqual(unavailable["uia"], "unqualified")
        self.assertTrue(unavailable["read_only"])
        self.attach()
        ready = self.get(capability_url).json()
        self.assertEqual(ready["collector"], "ready")

    def test_no_mutation_or_ingestion_http_method(self):
        self.attach()
        for action in ("POST", "PUT", "DELETE", "PATCH"):
            with self.subTest(action=action):
                result = self.client.request(action, URL, headers={"X-API-Key": TOKEN})
                self.assertEqual(result.status_code, 405)

    def test_handover_between_auth_and_response_fails_closed(self):
        self.attach()
        with patch(
            "api.routers.wine_events_rdte.read_session_dir",
            side_effect=[ROOT, "/tmp/synthetic/session-next"],
        ):
            result = self.get()
        self.assertEqual(result.status_code, 409)
        self.assertEqual(registry.observe(SESSION)["state"], "unavailable")


if __name__ == "__main__":
    import unittest
    unittest.main()
