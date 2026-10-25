"""Real FastAPI lifespan, synthetic no-process observer admission receipts."""
import asyncio
import os
import unittest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from api.server import app


async def idle():
    await asyncio.sleep(100)


class AppLifespanTests(unittest.TestCase):
    def do_lifespan(self, enabled):
        env = {
            "API_TOKEN": "synthetic-service-token",
            "WINEBOT_WINE_EVENTS_RDTE_ENABLED": "1" if enabled else "0",
            "WINEBOT_WINE_EVENTS_PROCESS_RDTE_ENABLED": "1" if enabled else "0",
        }
        supervisor = MagicMock()
        supervisor.start_if_admitted.return_value = False
        supervisor.shutdown.return_value = True
        with patch.dict(os.environ, env):
            with patch("api.server.validate_current_environment", return_value=[]):
                with patch("api.server.read_session_dir", return_value=None):
                    with patch("api.server.write_instance_state"):
                        with patch("api.server.append_lifecycle_event"):
                            with patch("api.server.discovery_manager.start"):
                                with patch("api.server.discovery_manager.stop"):
                                    with patch("api.server.reap_finished_tracked_processes"):
                                        with patch("api.server.inactivity_monitor_task", new=idle):
                                            with patch(
                                                "api.core.wine_events_service_rdte.service",
                                                new=supervisor,
                                            ):
                                                with TestClient(app) as client:
                                                    response = client.get(
                                                        "/version", headers={
                                                            "X-API-Key": "synthetic-service-token"
                                                        },
                                                    )
                                                    self.assertEqual(response.status_code, 200)
        return supervisor

    def test_opt_in_invokes_supervisor_and_shutdown(self):
        supervisor = self.do_lifespan(True)
        supervisor.start_if_admitted.assert_called()
        supervisor.shutdown.assert_called_once()

    def test_default_off_does_not_start_supervisor(self):
        supervisor = self.do_lifespan(False)
        supervisor.start_if_admitted.assert_not_called()
        supervisor.shutdown.assert_not_called()


if __name__ == "__main__":
    unittest.main()
