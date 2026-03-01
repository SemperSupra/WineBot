from fastapi.testclient import TestClient
from api.server import app
from unittest.mock import patch, AsyncMock
import os
import pytest

client = TestClient(app)


# Helper to mock token
@pytest.fixture
def auth_headers():
    return {"X-API-Key": "test-token"}


@patch("api.routers.health.safe_command")
@patch("api.routers.health.check_binary")
@patch("api.routers.health.statvfs_info")
@patch("os.path.isdir")
@patch("os.path.exists")
def test_health_check(
    mock_exists,
    mock_isdir,
    mock_statvfs,
    mock_check_binary,
    mock_safe_command,
    auth_headers,
):
    with patch.dict(os.environ, {"API_TOKEN": "test-token", "WINEBOT_RECORD": "1"}):
        mock_safe_command.return_value = {
            "ok": True,
            "stdout": "connected",
            "stderr": "",
        }
        mock_check_binary.return_value = {"present": True, "path": "/bin/tool"}
        mock_statvfs.return_value = {"ok": True, "writable": True}
        mock_isdir.return_value = True
        mock_exists.return_value = True
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
        # If any required tool is missing in real env, it might be degraded.
        # But our mock returns True for all.


@patch("subprocess.run")
def test_health_check_unauthorized(mock_run):
    with patch.dict(os.environ, {"API_TOKEN": "test-token", "WINEBOT_RECORD": "1"}):
        response = client.get("/health", headers={"X-API-Key": "wrong"})
        assert response.status_code == 403


@patch(
    "api.routers.health.meminfo_summary",
    return_value={"mem_total_kb": 1, "mem_available_kb": 1},
)
@patch("platform.node", return_value="test-host")
def test_health_system(_mock_node, _mock_meminfo, auth_headers):
    with patch.dict(os.environ, {"API_TOKEN": "test-token", "WINEBOT_RECORD": "1"}):
        response = client.get("/health/system", headers=auth_headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["hostname"] == "test-host"


@patch("api.routers.health.safe_async_command")
def test_health_x11(mock_safe_async_command, auth_headers):
    async def side_effect(cmd, timeout=5):
        if cmd[0] == "xdpyinfo":
            return {"ok": True}
        if cmd[0] == "/automation/x11.sh":
            return {"ok": True, "stdout": "0xabc"}
        return {"ok": False}

    mock_safe_async_command.side_effect = side_effect
    with patch.dict(os.environ, {"API_TOKEN": "test-token", "WINEBOT_RECORD": "1"}):
        response = client.get("/health/x11", headers=auth_headers)
        assert response.status_code == 200


@patch("api.routers.lifecycle.safe_command")
def test_openbox_reconfigure(mock_safe, auth_headers):
    mock_safe.return_value = {"ok": True, "stdout": "", "stderr": ""}
    with patch.dict(os.environ, {"API_TOKEN": "test-token", "WINEBOT_RECORD": "1"}):
        response = client.post("/openbox/reconfigure", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "reconfigured"


@patch("api.routers.recording.read_pid", return_value=123)
@patch("api.routers.recording.read_session_dir", return_value=None)
@patch("subprocess.Popen")
def test_recording_start(mock_popen, mock_read, mock_pid, tmp_path, auth_headers):
    with patch.dict(
        os.environ,
        {
            "API_TOKEN": "test-token",
            "WINEBOT_SESSION_ROOT": str(tmp_path),
            "WINEBOT_RECORD": "1",
        },
    ):
        response = client.post("/recording/start", headers=auth_headers, json={})
        assert response.status_code == 200
        body = response.json()
        assert body["action"] == "start"
        assert body["result"] == "converged"
        assert body["converged"] is True
        assert body.get("recording_timeline_id", "").startswith("timeline-")
        assert os.path.exists(os.path.join(body["session_dir"], "recording_artifacts_manifest.json"))


@patch("api.routers.recording.run_async_command", new_callable=AsyncMock)
@patch("api.routers.recording.recorder_running", side_effect=[True, False])
@patch("api.routers.recording.read_session_dir")
@patch("api.routers.recording.recorder_state", return_value="recording")
def test_recording_stop(
    mock_state, mock_read, mock_running, mock_run, tmp_path, auth_headers
):
    session_dir = tmp_path / "session-1"
    session_dir.mkdir()
    mock_read.return_value = str(session_dir)
    mock_run.return_value = {"ok": True, "stderr": ""}
    with patch.dict(os.environ, {"API_TOKEN": "test-token", "WINEBOT_RECORD": "1"}):
        response = client.post("/recording/stop", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["action"] == "stop"
        assert body["result"] == "converged"
        assert body["converged"] is True
        assert body.get("recording_timeline_id", "").startswith("timeline-")
        assert os.path.exists(
            os.path.join(str(session_dir), "recording_artifacts_manifest.json")
        )


@patch("api.routers.automation.safe_command")
@patch("api.routers.automation.validate_path")
def test_run_app(mock_validate, mock_run, auth_headers):
    mock_run.return_value = {"ok": True, "stdout": "Success", "stderr": ""}
    mock_validate.return_value = "/apps/test.exe"
    with patch.dict(os.environ, {"API_TOKEN": "test-token", "WINEBOT_RECORD": "1"}):
        with patch(
            "api.routers.automation.broker.check_access",
            new=AsyncMock(return_value=True),
        ):
            with patch(
                "api.routers.automation.broker.report_agent_activity",
                new=AsyncMock(),
            ):
                response = client.post(
                    "/apps/run", json={"path": "/apps/test.exe"}, headers=auth_headers
                )
        # Router returns 200 with status: finished
        assert response.status_code == 200
        assert response.json()["status"] == "finished"


@patch("api.routers.automation.validate_path")
def test_run_app_invalid_path(mock_validate, auth_headers):

    mock_validate.side_effect = Exception("Path not allowed")

    with patch.dict(os.environ, {"API_TOKEN": "test-token", "WINEBOT_RECORD": "1"}):
        with patch(
            "api.routers.automation.broker.check_access",
            new=AsyncMock(return_value=True),
        ):
            with patch(
                "api.routers.automation.broker.report_agent_activity",
                new=AsyncMock(),
            ):
                response = client.post(
                    "/apps/run", json={"path": "/etc/passwd"}, headers=auth_headers
                )

        assert response.status_code == 400


def test_version_endpoint_and_headers(auth_headers):
    with patch.dict(os.environ, {"API_TOKEN": "test-token", "WINEBOT_RECORD": "1"}):
        response = client.get("/version", headers=auth_headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["api_version"] == "1.0"
        assert payload["artifact_schema_version"] == "1.0"
        assert payload["event_schema_version"] == "1.0"
        assert response.headers["X-WineBot-API-Version"] == payload["api_version"]
        assert response.headers["X-WineBot-Build-Version"] == payload["version"]
        assert (
            response.headers["X-WineBot-Artifact-Schema-Version"]
            == payload["artifact_schema_version"]
        )
        assert (
            response.headers["X-WineBot-Event-Schema-Version"]
            == payload["event_schema_version"]
        )
