import os
import asyncio
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from fastapi import HTTPException

from api.core.models import RecorderState
from api.core.models import ControlPolicyMode
from api.server import app

client = TestClient(app)


def _auth():
    return {"X-API-Key": "test-token"}


def test_openbox_restart_endpoint():
    with patch.dict(os.environ, {"API_TOKEN": "test-token", "MODE": "interactive"}):
        with patch("api.routers.lifecycle.safe_command") as mock_safe:
            response = client.post("/openbox/restart", headers=_auth())
    assert response.status_code == 200
    assert response.json()["status"] == "restarted"
    mock_safe.assert_called_once_with(["openbox", "--restart"])


def test_lifecycle_reset_workspace_starts_explorer_when_missing():
    with patch.dict(os.environ, {"API_TOKEN": "test-token", "MODE": "interactive"}):
        with patch("api.routers.lifecycle.find_processes", return_value=[]):
            with patch("api.routers.lifecycle.subprocess.Popen") as mock_popen:
                with patch("api.routers.lifecycle.subprocess.run") as mock_run:
                    response = client.post("/lifecycle/reset_workspace", headers=_auth())
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    mock_popen.assert_called_once()
    mock_run.assert_called_once()


def test_recording_pause_and_resume_contract():
    with patch.dict(os.environ, {"API_TOKEN": "test-token", "WINEBOT_RECORD": "1"}):
        with patch("api.routers.recording.read_session_dir", return_value="/tmp/s1"):
            with patch("api.routers.recording.recorder_running", return_value=True):
                with patch(
                    "api.routers.recording.recorder_state",
                    side_effect=[
                        RecorderState.PAUSED.value,  # pause: already paused
                        RecorderState.PAUSED.value,  # resume: precondition
                        RecorderState.RECORDING.value,  # resume settle loop
                    ],
                ):
                    with patch(
                        "api.routers.recording.run_async_command",
                        new_callable=AsyncMock,
                    ) as mock_run:
                        mock_run.return_value = {"ok": True, "stderr": ""}
                        pause_res = client.post("/recording/pause", headers=_auth())
                        resume_res = client.post("/recording/resume", headers=_auth())

    assert pause_res.status_code == 200
    pause_body = pause_res.json()
    assert pause_body["status"] == "already_paused"
    assert pause_body["action"] == "pause"
    assert pause_body["result"] == "converged"
    assert pause_body["converged"] is True
    assert resume_res.status_code == 200
    resume_body = resume_res.json()
    assert resume_body["status"] == "resumed"
    assert resume_body["action"] == "resume"
    assert resume_body["result"] == "converged"
    assert resume_body["converged"] is True


def test_recording_resume_requested_contract():
    with patch.dict(os.environ, {"API_TOKEN": "test-token", "WINEBOT_RECORD": "1"}):
        with patch("api.routers.recording.read_session_dir", return_value="/tmp/s1"):
            with patch("api.routers.recording.recorder_running", return_value=True):
                with patch(
                    "api.routers.recording.recorder_state",
                    return_value=RecorderState.PAUSED.value,
                ):
                    with patch(
                        "api.routers.recording.run_async_command",
                        new_callable=AsyncMock,
                    ) as mock_run:
                        with patch(
                            "api.routers.recording.asyncio.sleep", new=AsyncMock()
                        ):
                            mock_run.return_value = {"ok": True, "stderr": ""}
                            response = client.post("/recording/resume", headers=_auth())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resume_requested"
    assert body["action"] == "resume"
    assert body["result"] == "accepted"
    assert body["converged"] is False
    assert body.get("recording_timeline_id", "").startswith("timeline-")


def test_recording_stop_requested_contract():
    with patch.dict(os.environ, {"API_TOKEN": "test-token", "WINEBOT_RECORD": "1"}):
        with patch("api.routers.recording.read_session_dir", return_value="/tmp/s1"):
            with patch("api.routers.recording.recorder_running", return_value=True):
                with patch(
                    "api.routers.recording.run_async_command",
                    new_callable=AsyncMock,
                ) as mock_run:
                    with patch("api.routers.recording._int_env", return_value=1):
                        with patch(
                            "api.routers.recording.asyncio.sleep", new=AsyncMock()
                        ):
                            mock_run.return_value = {"ok": True, "stderr": ""}
                            response = client.post("/recording/stop", headers=_auth())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "stop_requested"
    assert body["action"] == "stop"
    assert body["result"] == "accepted"
    assert body["converged"] is False
    assert "warning" in body
    assert body.get("recording_timeline_id", "").startswith("timeline-")


def test_recording_openapi_response_models():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.get("/openapi.json")
    assert response.status_code == 200
    payload = response.json()
    stop_schema = payload["paths"]["/recording/stop"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    start_schema = payload["paths"]["/recording/start"]["post"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert stop_schema["$ref"].endswith("/RecordingActionResponse")
    assert start_schema["$ref"].endswith("/RecordingStartResponse")


def test_recording_perf_summary_contract(tmp_path):
    session_dir = tmp_path / "session-1"
    logs_dir = session_dir / "logs"
    logs_dir.mkdir(parents=True)
    perf_path = logs_dir / "perf_metrics.jsonl"
    perf_path.write_text(
        "\n".join(
            [
                '{"event":"performance_metric","metric":"recording.api_pause.latency","value_ms":10}',
                '{"event":"performance_metric","metric":"recording.api_pause.latency","value_ms":20}',
                '{"event":"performance_metric","metric":"recording.api_resume.latency","value_ms":30}',
            ]
        ),
        encoding="utf-8",
    )

    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch("api.routers.recording.read_session_dir", return_value=str(session_dir)):
            response = client.get("/recording/perf/summary", headers=_auth())

    assert response.status_code == 200
    data = response.json()
    assert data["session_dir"] == str(session_dir)
    assert data["metrics"]["recording.api_pause.latency"]["count"] == 2
    assert data["metrics"]["recording.api_pause.latency"]["p50_ms"] == 10.0
    assert data["metrics"]["recording.api_pause.latency"]["max_ms"] == 20.0


def test_windows_focus_endpoint():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch(
            "api.routers.automation.broker.check_access",
            new=AsyncMock(return_value=True),
        ):
            with patch("api.routers.automation.safe_command") as mock_safe:
                response = client.post(
                    "/windows/focus",
                    json={"window_id": "0x1234"},
                    headers=_auth(),
                )
    assert response.status_code == 200
    assert response.json()["status"] == "focused"
    mock_safe.assert_called_once_with(
        ["/automation/bin/x11.sh", "focus-window", "0x1234"]
    )


def test_run_autoit_and_run_python_endpoints():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch(
            "api.routers.automation.broker.check_access",
            new=AsyncMock(return_value=True),
        ):
            with patch(
                "api.routers.automation.broker.report_agent_activity",
                new=AsyncMock(),
            ):
                with patch(
                    "api.routers.automation._require_active_session",
                    return_value="/tmp/winebot-session",
                ):
                    with patch("api.routers.automation.safe_command") as mock_safe:
                        mock_safe.return_value = {"ok": True, "stdout": "ok"}
                        autoit_res = client.post(
                            "/run/autoit",
                            json={"script": "MsgBox(0, 'a', 'b')"},
                            headers=_auth(),
                        )
                        python_res = client.post(
                            "/run/python",
                            json={"script": "print('ok')"},
                            headers=_auth(),
                        )
    assert autoit_res.status_code == 200
    assert autoit_res.json()["status"] == "ok"
    assert python_res.status_code == 200
    assert python_res.json()["status"] == "ok"


def test_control_endpoints_contract():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch(
            "api.routers.control.broker.grant_agent",
            new=AsyncMock(),
        ):
            with patch(
                "api.routers.control.broker.renew_agent",
                new=AsyncMock(),
            ):
                with patch(
                    "api.routers.control.broker.set_user_intent",
                    new=AsyncMock(),
                ):
                    with patch("api.routers.control.broker.get_state") as mock_state:
                        mock_state.return_value = {
                            "session_id": "s",
                            "interactive": True,
                            "control_mode": "AGENT",
                            "lease_expiry": None,
                            "user_intent": "WAIT",
                            "agent_status": "RUNNING",
                        }
                        with patch(
                            "api.routers.control.read_session_dir",
                            return_value="/tmp/abc",
                        ):
                            challenge_res = client.post(
                                "/sessions/abc/control/challenge", headers=_auth()
                            )
                            grant_res = client.post(
                                "/sessions/abc/control/grant",
                                json={
                                    "lease_seconds": 30,
                                    "user_ack": True,
                                    "challenge_token": "tok",
                                },
                                headers=_auth(),
                            )
                            renew_res = client.post(
                                "/sessions/abc/control/renew",
                                json={"lease_seconds": 30},
                                headers=_auth(),
                            )
                            intent_res = client.post(
                                "/sessions/abc/user_intent",
                                json={"intent": "WAIT"},
                                headers=_auth(),
                            )
                            get_res = client.get("/sessions/abc/control", headers=_auth())
    assert challenge_res.status_code == 200
    assert get_res.status_code == 200
    assert grant_res.status_code == 200
    assert renew_res.status_code == 200
    assert intent_res.status_code == 200


def test_trace_client_and_network_status_contract():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch("api.routers.input.read_session_dir", return_value="/tmp/s1"):
            with patch("api.routers.input.input_trace_client_enabled", return_value=True):
                with patch(
                    "api.routers.input.input_trace_client_log_path",
                    return_value="/tmp/s1/logs/input_events_client.jsonl",
                ):
                    with patch("api.routers.input.input_trace_network_pid", return_value=11):
                        with patch(
                            "api.routers.input.input_trace_network_running",
                            return_value=True,
                        ):
                            with patch(
                                "api.routers.input.input_trace_network_state",
                                return_value="enabled",
                            ):
                                with patch(
                                    "api.routers.input.input_trace_network_log_path",
                                    return_value="/tmp/s1/logs/input_events_network.jsonl",
                                ):
                                    client_res = client.get(
                                        "/input/trace/client/status", headers=_auth()
                                    )
                                    network_res = client.get(
                                        "/input/trace/network/status", headers=_auth()
                                    )

    assert client_res.status_code == 200
    assert client_res.json()["enabled"] is True
    assert network_res.status_code == 200
    assert network_res.json()["running"] is True


def test_control_mode_endpoints_contract(tmp_path):
    session_dir = tmp_path / "session-1"
    session_dir.mkdir()
    with patch.dict(os.environ, {"API_TOKEN": "test-token", "MODE": "interactive"}):
        with patch(
            "api.routers.control.resolve_session_dir", return_value=str(session_dir)
        ):
            with patch(
                "api.routers.control.read_session_dir", return_value="/tmp/not-active"
            ):
                get_res = client.get("/control/mode", headers=_auth())
                set_instance_res = client.post(
                    "/control/mode",
                    json={"mode": "hybrid"},
                    headers=_auth(),
                )
                set_session_res = client.post(
                    "/sessions/session-1/control/mode?allow_inactive=true",
                    json={"mode": "human-only"},
                    headers=_auth(),
                )
                get_session_res = client.get(
                    "/sessions/session-1/control/mode", headers=_auth()
                )
    assert get_res.status_code == 200
    assert set_instance_res.status_code == 200
    assert set_session_res.status_code == 200
    assert get_session_res.status_code == 200


def test_control_mode_set_active_check_happens_before_write(tmp_path):
    session_dir = tmp_path / "session-1"
    session_dir.mkdir()
    with patch.dict(os.environ, {"API_TOKEN": "test-token", "MODE": "interactive"}):
        with patch(
            "api.routers.control.resolve_session_dir", return_value=str(session_dir)
        ):
            with patch("api.routers.control.read_session_dir", return_value="/tmp/not-active"):
                with patch("api.routers.control.write_session_control_mode") as write_mode:
                    response = client.post(
                        "/sessions/session-1/control/mode",
                        json={"mode": "human-only"},
                        headers=_auth(),
                    )
    assert response.status_code == 409
    write_mode.assert_not_called()


def test_control_renew_requires_active_session():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch("api.routers.control.read_session_dir", return_value="/tmp/other"):
            response = client.post(
                "/sessions/abc/control/renew",
                json={"lease_seconds": 30},
                headers=_auth(),
            )
    assert response.status_code == 409


def test_control_mode_admission_blocks_headless_human_only():
    class _State:
        instance_control_mode = ControlPolicyMode.AGENT_ONLY
        session_control_mode = ControlPolicyMode.AGENT_ONLY
        effective_control_mode = ControlPolicyMode.AGENT_ONLY

    with patch.dict(
        os.environ,
        {"API_TOKEN": "test-token", "MODE": "headless", "WINEBOT_ALLOW_HEADLESS_HYBRID": "0"},
    ):
        with patch("api.routers.control.broker.get_state", return_value=_State()):
            res = client.post(
                "/control/mode",
                json={"mode": "human-only"},
                headers=_auth(),
            )
    assert res.status_code == 409


def test_input_events_limit_rejects_above_cap():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch("api.routers.input.config.WINEBOT_MAX_EVENTS_QUERY", 10):
            response = client.get("/input/events?limit=11", headers=_auth())
    assert response.status_code == 400
    assert "limit must be <=" in response.json()["detail"]


def test_lifecycle_events_limit_rejects_above_cap():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch("api.routers.lifecycle.config.WINEBOT_MAX_EVENTS_QUERY", 8):
            response = client.get("/lifecycle/events?limit=9", headers=_auth())
    assert response.status_code == 400
    assert "limit must be <=" in response.json()["detail"]


def test_sessions_list_limit_rejects_above_cap():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch("api.routers.lifecycle.config.WINEBOT_MAX_SESSIONS_QUERY", 5):
            response = client.get("/sessions?limit=6", headers=_auth())
    assert response.status_code == 400
    assert "limit must be <=" in response.json()["detail"]


def test_logs_tail_lines_limit_rejects_above_cap():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch("api.server.config.WINEBOT_MAX_LOG_TAIL_LINES", 20):
            response = client.get("/logs/tail?lines=21", headers=_auth())
    assert response.status_code == 400
    assert "lines must be <=" in response.json()["detail"]


def test_logs_tail_follow_stream_limit_rejects_when_exhausted():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch("api.utils.files.read_session_dir", return_value="/tmp/s1"):
            with patch("api.server.os.path.exists", return_value=True):
                with patch("api.server._follow_stream_semaphore", asyncio.Semaphore(0)):
                    response = client.get("/logs/tail?follow=true", headers=_auth())
    assert response.status_code == 429
    assert "Too many active log follow streams" in response.json()["detail"]


def test_lifecycle_shutdown_exposes_operation_status(tmp_path):
    session_dir = tmp_path / "session-op"
    session_dir.mkdir()

    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch("api.routers.lifecycle.read_session_dir", return_value=str(session_dir)):
            with patch("api.routers.lifecycle.append_lifecycle_event"):
                with patch("api.routers.lifecycle.write_instance_state"):
                    with patch(
                        "api.routers.lifecycle.atomic_shutdown",
                        new=AsyncMock(return_value={"ok": True}),
                    ):
                        with patch("api.routers.lifecycle.schedule_shutdown"):
                            response = client.post("/lifecycle/shutdown", headers=_auth())

    assert response.status_code == 200
    body = response.json()
    op_id = body.get("operation_id")
    assert op_id

    op_res = client.get(f"/operations/{op_id}", headers=_auth())
    assert op_res.status_code == 200
    op = op_res.json()
    assert op["status"] == "succeeded"
    assert op["kind"] == "lifecycle_shutdown"


def test_resume_session_rolls_back_state_on_broker_failure(tmp_path):
    current_dir = tmp_path / "session-current"
    target_dir = tmp_path / "session-target"
    current_dir.mkdir()
    target_dir.mkdir()
    (current_dir / "session.json").write_text("{}", encoding="utf-8")
    (target_dir / "session.json").write_text("{}", encoding="utf-8")
    (current_dir / "session.state").write_text("active", encoding="utf-8")
    (target_dir / "session.state").write_text("suspended", encoding="utf-8")

    with patch.dict(os.environ, {"API_TOKEN": "test-token", "MODE": "interactive"}):
        with patch("api.routers.lifecycle.read_session_dir", return_value=str(current_dir)):
            with patch("api.routers.lifecycle.resolve_session_dir", return_value=str(target_dir)):
                with patch("api.routers.lifecycle.append_lifecycle_event"):
                    with patch("api.routers.lifecycle.link_wine_user_dir"):
                        with patch("api.routers.lifecycle.ensure_user_profile"):
                            with patch(
                                "api.routers.lifecycle.atomic_shutdown",
                                new=AsyncMock(return_value={"ok": True}),
                            ):
                                with patch(
                                    "api.routers.lifecycle.broker.update_session",
                                    new=AsyncMock(
                                        side_effect=HTTPException(
                                            status_code=500, detail="broker update failed"
                                        )
                                    ),
                                ):
                                    response = client.post(
                                        "/sessions/resume",
                                        json={"session_dir": str(target_dir)},
                                        headers=_auth(),
                                    )

    assert response.status_code == 500
    assert (target_dir / "session.state").read_text(encoding="utf-8").strip() == "suspended"
    assert (current_dir / "session.state").read_text(encoding="utf-8").strip() == "active"


def test_recording_stop_returns_operation_id(tmp_path):
    session_dir = tmp_path / "session-rec-stop"
    session_dir.mkdir()
    (session_dir / "session.json").write_text("{}", encoding="utf-8")

    with patch.dict(os.environ, {"API_TOKEN": "test-token", "WINEBOT_RECORD": "1"}):
        with patch("api.routers.recording.read_session_dir", return_value=str(session_dir)):
            with patch("api.routers.recording.recorder_running", return_value=False):
                response = client.post("/recording/stop", headers=_auth())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "already_stopped"
    assert body["action"] == "stop"
    assert body["result"] == "converged"
    assert body["converged"] is True
    assert body.get("operation_id")
