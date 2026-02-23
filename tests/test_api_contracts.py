import os
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

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
                    return_value=RecorderState.PAUSED.value,
                ):
                    with patch(
                        "api.routers.recording.run_async_command",
                        new_callable=AsyncMock,
                    ) as mock_run:
                        mock_run.return_value = {"ok": True, "stderr": ""}
                        pause_res = client.post("/recording/pause", headers=_auth())
                        resume_res = client.post("/recording/resume", headers=_auth())

    assert pause_res.status_code == 200
    assert pause_res.json()["status"] == "already_paused"
    assert resume_res.status_code == 200
    assert resume_res.json()["status"] == "resumed"


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
