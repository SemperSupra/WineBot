import os
import asyncio
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from api.server import app
from api.core.broker import InputBroker
from api.core.models import ControlMode

client = TestClient(app)


def test_sessions_resume_concurrent_calls_idempotent(tmp_path):
    session_dir = tmp_path / "session-1"
    session_dir.mkdir()
    (session_dir / "session.json").write_text("{}")
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch(
            "api.routers.lifecycle.read_session_dir",
            side_effect=[None, str(session_dir), str(session_dir)],
        ):
            with patch("api.routers.lifecycle.write_session_dir"):
                with patch("api.routers.lifecycle.write_session_state"):
                    with patch("api.routers.lifecycle.append_lifecycle_event"):
                        with patch("api.routers.lifecycle.link_wine_user_dir"):
                            with patch("api.routers.lifecycle.ensure_user_profile"):
                                with patch("api.routers.lifecycle.broker.update_session"):
                                    res1 = client.post(
                                        "/sessions/resume",
                                        json={"session_dir": str(session_dir)},
                                        headers={"X-API-Key": "test-token"},
                                    )
                                    res2 = client.post(
                                        "/sessions/resume",
                                        json={"session_dir": str(session_dir)},
                                        headers={"X-API-Key": "test-token"},
                                    )
    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res1.json()["status"] == "resumed"
    assert res2.json()["status"] == "already_active"


def test_sessions_suspend_no_active_session():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch("api.routers.lifecycle.read_session_dir", return_value=None):
            response = client.post(
                "/sessions/suspend", headers={"X-API-Key": "test-token"}
            )
    assert response.status_code == 404
    assert response.json()["detail"] == "No active session to suspend"


def test_sessions_suspend_oneshot_marks_completed(tmp_path):
    session_dir = tmp_path / "session-oneshot"
    session_dir.mkdir()
    (session_dir / "session.json").write_text("{}", encoding="utf-8")
    with patch.dict(
        os.environ,
        {"API_TOKEN": "test-token", "WINEBOT_SESSION_MODE": "oneshot"},
    ):
        with patch("api.routers.lifecycle.read_session_dir", return_value=str(session_dir)):
            with patch("api.routers.lifecycle.graceful_wine_shutdown"):
                response = client.post(
                    "/sessions/suspend",
                    headers={"X-API-Key": "test-token"},
                )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["session_mode"] == "oneshot"


def test_sessions_resume_completed_oneshot_conflict(tmp_path):
    session_dir = tmp_path / "session-finished"
    session_dir.mkdir()
    (session_dir / "session.json").write_text("{}", encoding="utf-8")
    (session_dir / "session.mode").write_text("oneshot", encoding="utf-8")
    (session_dir / "session.state").write_text("completed", encoding="utf-8")
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.post(
            "/sessions/resume",
            json={"session_dir": str(session_dir)},
            headers={"X-API-Key": "test-token"},
        )
    assert response.status_code == 409
    assert "cannot be resumed" in response.json()["detail"]


def test_sessions_resume_non_existent_dir():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.post(
            "/sessions/resume",
            json={"session_dir": "/artifacts/sessions/nonexistent"},
            headers={"X-API-Key": "test-token"},
        )
    assert response.status_code == 404
    assert response.json()["detail"] == "Session directory not found"


def test_sessions_resume_path_not_allowed():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.post(
            "/sessions/resume",
            json={"session_dir": "/etc/passwd"},
            headers={"X-API-Key": "test-token"},
        )
    assert response.status_code == 400
    assert "Path not allowed" in response.json()["detail"]


def test_lifecycle_shutdown_power_off(tmp_path):
    session_dir = tmp_path / "active-session"
    session_dir.mkdir()

    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch(
            "api.routers.lifecycle.read_session_dir", return_value=str(session_dir)
        ):
            with patch("api.routers.lifecycle.append_lifecycle_event"):
                with patch(
                    "api.routers.lifecycle.safe_command", return_value={"ok": True}
                ):
                    with patch("api.routers.lifecycle.schedule_shutdown"):
                        client.post(
                            "/lifecycle/shutdown?power_off=true",
                            headers={"X-API-Key": "test-token"},
                        )


def test_lifecycle_shutdown_idempotent_guard(tmp_path):
    session_dir = tmp_path / "active-session"
    session_dir.mkdir()

    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch(
            "api.routers.lifecycle.read_session_dir", return_value=str(session_dir)
        ):
            with patch("api.routers.lifecycle.append_lifecycle_event"):
                with patch("api.routers.lifecycle.atomic_shutdown", return_value={"ok": True}):
                    with patch("api.routers.lifecycle.schedule_shutdown"):
                        import api.routers.lifecycle as lifecycle_router

                        lifecycle_router._shutdown_in_progress = False
                        lifecycle_router._shutdown_mode = ""
                        lifecycle_router._shutdown_started_at = 0.0

                        res1 = client.post(
                            "/lifecycle/shutdown",
                            headers={"X-API-Key": "test-token"},
                        )
                        res2 = client.post(
                            "/lifecycle/shutdown",
                            headers={"X-API-Key": "test-token"},
                        )

    assert res1.status_code == 200
    assert res1.json()["status"] == "shutting_down"
    assert res2.status_code == 200
    assert res2.json()["status"] == "already_shutting_down"


@pytest.mark.anyio
async def test_broker_concurrency_renew_vs_revoke():
    broker = InputBroker()
    await broker.update_session("test", interactive=True)
    challenge = await broker.issue_grant_challenge()
    await broker.grant_agent(10, user_ack=True, challenge_token=challenge["token"])

    # Simulate concurrent renew and user activity (revoke)
    # renewals should fail if revoke wins
    async def task_renew():
        try:
            await broker.renew_agent(10)
            return "renewed"
        except Exception:
            return "failed"

    async def task_revoke():
        await broker.report_user_activity()
        return "revoked"

    results = await asyncio.gather(task_renew(), task_revoke())

    state = broker.get_state()
    assert state.control_mode == ControlMode.USER
    # One of them must have happened first.
    # If revoke happened first, renew fails.
    # If renew happened first, revoke still works and final state is USER.
    assert "revoked" in results
