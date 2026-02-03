from fastapi.testclient import TestClient
from api.server import app
from unittest.mock import patch, MagicMock
import os
import pytest
from pathlib import Path

client = TestClient(app)

# Helper to mock token
@pytest.fixture
def auth_headers():
    return {"X-API-Key": "test-token"}

@patch("api.server.safe_command")
@patch("api.server.check_binary")
@patch("api.server.statvfs_info")
@patch("os.path.isdir")
@patch("os.path.exists")
def test_health_check(mock_exists, mock_isdir, mock_statvfs, mock_check_binary, mock_safe_command, auth_headers):
    # Mock env var
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        mock_safe_command.return_value = {"ok": True, "stdout": "", "stderr": ""}
        mock_check_binary.return_value = {"present": True, "path": "/bin/tool"}
        mock_statvfs.return_value = {"ok": True, "writable": True}
        mock_isdir.return_value = True
        mock_exists.return_value = True
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["x11"] == "connected"
        assert payload["wineprefix"] == "ready"
        assert payload["tools_ok"] is True
        assert payload["storage_ok"] is True

@patch("subprocess.run")
def test_health_check_unauthorized(mock_run):
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.get("/health", headers={"X-API-Key": "wrong"})
        assert response.status_code == 403

@patch("api.server.safe_command")
@patch("api.server.check_binary")
@patch("api.server.statvfs_info")
@patch("os.path.isdir")
@patch("os.path.exists")
def test_health_check_no_token_required(mock_exists, mock_isdir, mock_statvfs, mock_check_binary, mock_safe_command):
    # No API_TOKEN env var set
    with patch.dict(os.environ, {}, clear=True):
        mock_safe_command.return_value = {"ok": True, "stdout": "", "stderr": ""}
        mock_check_binary.return_value = {"present": True, "path": "/bin/tool"}
        mock_statvfs.return_value = {"ok": True, "writable": True}
        mock_isdir.return_value = True
        mock_exists.return_value = True
        response = client.get("/health") # No header
        assert response.status_code == 200

@patch("api.server.meminfo_summary", return_value={"mem_total_kb": 1, "mem_available_kb": 1})
@patch("platform.node", return_value="test-host")
def test_health_system(_mock_node, _mock_meminfo, auth_headers):
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.get("/health/system", headers=auth_headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["hostname"] == "test-host"
        assert "uptime_seconds" in payload

@patch("api.server.safe_command")
def test_health_x11(mock_safe_command, auth_headers):
    def side_effect(cmd, timeout=5):
        if cmd[0] == "xdpyinfo":
            return {"ok": True}
        if cmd[:2] == ["pgrep", "-x"]:
            return {"ok": True, "stdout": "123"}
        if cmd[0] == "/automation/x11.sh":
            return {"ok": True, "stdout": "0xabc"}
        return {"ok": False}
    mock_safe_command.side_effect = side_effect
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.get("/health/x11", headers=auth_headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["connected"] is True

@patch("api.server.safe_command")
def test_health_windows(mock_safe_command, auth_headers):
    def side_effect(cmd, timeout=5):
        if cmd[0] == "/automation/x11.sh" and cmd[1] == "list-windows":
            return {"ok": True, "stdout": "0x1 Title One\n0x2 Title Two"}
        if cmd[0] == "/automation/x11.sh" and cmd[1] == "active-window":
            return {"ok": True, "stdout": "0x1"}
        return {"ok": False}
    mock_safe_command.side_effect = side_effect
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.get("/health/windows", headers=auth_headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 2

@patch("api.server.safe_command")
@patch("os.path.isdir")
@patch("os.path.exists")
def test_health_wine(mock_exists, mock_isdir, mock_safe_command, auth_headers):
    mock_exists.return_value = True
    mock_isdir.return_value = True
    mock_safe_command.return_value = {"ok": True, "stdout": "wine-9.0"}
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.get("/health/wine", headers=auth_headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["prefix_exists"] is True
        assert payload["system_reg_exists"] is True

@patch("api.server.check_binary")
def test_health_tools(mock_check_binary, auth_headers):
    mock_check_binary.return_value = {"present": True, "path": "/bin/tool"}
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.get("/health/tools", headers=auth_headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True

@patch("api.server.statvfs_info")
def test_health_storage(mock_statvfs, auth_headers):
    mock_statvfs.return_value = {"ok": True, "writable": True}
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.get("/health/storage", headers=auth_headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["ok"] is True

@patch("api.server.safe_command")
@patch("os.path.exists")
def test_health_recording(mock_exists, mock_safe_command, auth_headers):
    mock_exists.return_value = False
    mock_safe_command.return_value = {"ok": False}
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.get("/health/recording", headers=auth_headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["enabled"] in (True, False)

def test_ui_dashboard_served(auth_headers):
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.get("/ui", headers=auth_headers)
        assert response.status_code == 200
        assert "id=\"vnc-container\"" in response.text
        assert "id=\"control-panel\"" in response.text
        assert "id=\"btn-shutdown\"" in response.text
        assert "id=\"btn-poweroff\"" in response.text
        assert "id=\"lifecycle-events\"" in response.text

def test_ui_dashboard_no_token_required():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.get("/ui")
        assert response.status_code == 200

def test_recording_start_creates_session(tmp_path, auth_headers):
    session_file = tmp_path / "session_file"
    with patch.dict(os.environ, {"API_TOKEN": "test-token", "WINEBOT_SESSION_ROOT": str(tmp_path), "SCREEN": "800x600x24"}):
        with patch("api.server.SESSION_FILE", str(session_file)):
            with patch("subprocess.Popen") as mock_popen:
                response = client.post("/recording/start", headers=auth_headers, json={})
                assert response.status_code == 200
                payload = response.json()
                assert "session_dir" in payload
                assert "output_file" in payload
                assert Path(session_file).exists()
                assert Path(session_file).read_text().strip() == payload["session_dir"]
                mock_popen.assert_called_once()

def test_recording_stop_keeps_session(tmp_path, auth_headers):
    session_dir = tmp_path / "session-1"
    session_dir.mkdir()
    (session_dir / "recorder.pid").write_text("123")
    session_file = tmp_path / "session_file"
    session_file.write_text(str(session_dir))
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch("api.server.SESSION_FILE", str(session_file)):
            with patch("api.server.pid_running", return_value=False):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value.returncode = 0
                    mock_run.return_value.stderr = ""
                    response = client.post("/recording/stop", headers=auth_headers)
                    assert response.status_code == 200
                    assert session_file.exists()

def test_recording_pause_resume(tmp_path, auth_headers):
    session_dir = tmp_path / "session-2"
    session_dir.mkdir()
    session_file = tmp_path / "session_file"
    session_file.write_text(str(session_dir))
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch("api.server.SESSION_FILE", str(session_file)):
            with patch("api.server.recorder_running", return_value=True):
                with patch("api.server.recorder_state", return_value="recording"):
                    with patch("subprocess.run") as mock_run:
                        mock_run.return_value.returncode = 0
                        mock_run.return_value.stderr = ""
                        response = client.post("/recording/pause", headers=auth_headers)
                        assert response.status_code == 200
                with patch("api.server.recorder_state", return_value="paused"):
                    with patch("subprocess.run") as mock_run:
                        mock_run.return_value.returncode = 0
                        mock_run.return_value.stderr = ""
                        response = client.post("/recording/resume", headers=auth_headers)
                        assert response.status_code == 200

def test_recording_idempotent_actions(tmp_path, auth_headers):
    session_dir = tmp_path / "session-3"
    session_dir.mkdir()
    session_file = tmp_path / "session_file"
    session_file.write_text(str(session_dir))
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch("api.server.SESSION_FILE", str(session_file)):
            with patch("api.server.recorder_running", return_value=True):
                with patch("api.server.recorder_state", return_value="recording"):
                    response = client.post("/recording/start", headers=auth_headers, json={})
                    assert response.status_code == 200
                    assert response.json()["status"] == "already_recording"
            with patch("api.server.recorder_running", return_value=False):
                response = client.post("/recording/stop", headers=auth_headers)
                assert response.status_code == 200
                assert response.json()["status"] == "already_stopped"
            response = client.post("/recording/pause", headers=auth_headers)
            assert response.status_code == 200
            response = client.post("/recording/resume", headers=auth_headers)
            assert response.status_code == 200

@patch("subprocess.run")
def test_run_app_valid_path(mock_run, auth_headers):
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.post("/apps/run", json={"path": "/apps/app.exe"}, headers=auth_headers)
        assert response.status_code == 200
        # Check command
        args = mock_run.call_args[0][0]
        assert args[1] == "/apps/app.exe"

@patch("subprocess.run")
def test_run_app_invalid_path(mock_run, auth_headers):
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.post("/apps/run", json={"path": "/etc/passwd"}, headers=auth_headers)
        assert response.status_code == 400
        assert "Path not allowed" in response.json()["detail"]

@patch("subprocess.run")
def test_list_windows(mock_run, auth_headers):
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        mock_run.return_value.stdout = "0x123456 Title 1\n0x789abc Title 2"
        response = client.get("/windows", headers=auth_headers)
        assert response.status_code == 200
        assert len(response.json()["windows"]) == 2

@patch("subprocess.run")
def test_focus_window(mock_run, auth_headers):
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.post("/windows/focus", json={"window_id": "0x123"}, headers=auth_headers)
        assert response.status_code == 200

@patch("subprocess.run")
def test_click_at(mock_run, auth_headers):
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.post("/input/mouse/click", json={"x": 100, "y": 200}, headers=auth_headers)
        assert response.status_code == 200

def test_screenshot_output_dir_header(tmp_path, auth_headers):
    out_dir = tmp_path / "shots"
    out_dir.mkdir()
    shot_path = out_dir / "screenshot_123.png"
    shot_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch("api.server.time.time", return_value=123):
            with patch("api.server.run_command"):
                response = client.get(f"/screenshot?output_dir={out_dir}", headers=auth_headers)
                assert response.status_code == 200
                assert response.headers.get("X-Screenshot-Path") == str(shot_path)

@patch("api.server.safe_command")
def test_lifecycle_status(mock_safe, auth_headers):
    mock_safe.return_value = {"ok": False}
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.get("/lifecycle/status", headers=auth_headers)
        assert response.status_code == 200
        payload = response.json()
        assert "processes" in payload
        assert "session_dir" in payload

def test_lifecycle_events(tmp_path, auth_headers):
    session_dir = tmp_path / "session-1"
    logs_dir = session_dir / "logs"
    logs_dir.mkdir(parents=True)
    log_path = logs_dir / "lifecycle.jsonl"
    log_path.write_text('{"kind":"one"}\n{"kind":"two"}\n')
    session_file = tmp_path / "session_file"
    session_file.write_text(str(session_dir))
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch("api.server.SESSION_FILE", str(session_file)):
            response = client.get("/lifecycle/events?limit=1", headers=auth_headers)
            assert response.status_code == 200
            events = response.json()["events"]
            assert len(events) == 1
            assert events[0]["kind"] == "two"

@patch("api.server.schedule_shutdown")
def test_lifecycle_shutdown(mock_shutdown, tmp_path, auth_headers):
    session_dir = tmp_path / "session-2"
    (session_dir / "logs").mkdir(parents=True)
    session_file = tmp_path / "session_file"
    session_file.write_text(str(session_dir))
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch("api.server.SESSION_FILE", str(session_file)):
            with patch("api.server.graceful_wine_shutdown", return_value={"wineboot": {"ok": True}}):
                with patch("api.server.graceful_component_shutdown", return_value={"xvfb": {"ok": True}}):
                    with patch("api.server.recorder_running", return_value=False):
                        response = client.post("/lifecycle/shutdown", headers=auth_headers)
                        assert response.status_code == 200
                        payload = response.json()
                        assert payload["status"] == "shutting_down"
                        assert "wine_shutdown" in payload
                        assert "component_shutdown" in payload

@patch("api.server.schedule_shutdown")
def test_lifecycle_power_off(mock_shutdown, tmp_path, auth_headers):
    session_dir = tmp_path / "session-3"
    (session_dir / "logs").mkdir(parents=True)
    session_file = tmp_path / "session_file"
    session_file.write_text(str(session_dir))
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        with patch("api.server.SESSION_FILE", str(session_file)):
            response = client.post("/lifecycle/shutdown?power_off=true", headers=auth_headers)
            assert response.status_code == 200
            payload = response.json()
            assert payload["status"] == "powering_off"

@patch("subprocess.run")
@patch("builtins.open", new_callable=MagicMock)
@patch("os.path.exists")
def test_run_ahk(mock_exists, mock_open, mock_run, auth_headers):
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        mock_exists.return_value = True 
        mock_run.return_value.returncode = 0
        response = client.post("/run/ahk", json={"script": "MsgBox"}, headers=auth_headers)
        assert response.status_code == 200

@patch("subprocess.run")
@patch("builtins.open", new_callable=MagicMock)
@patch("os.path.exists")
def test_run_autoit(mock_exists, mock_open, mock_run, auth_headers):
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        mock_exists.return_value = True
        mock_run.return_value.returncode = 0
        response = client.post("/run/autoit", json={"script": "MsgBox"}, headers=auth_headers)
        assert response.status_code == 200

@patch("subprocess.run")
@patch("builtins.open", new_callable=MagicMock)
def test_run_python(mock_open, mock_run, auth_headers):
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "Hello"
        response = client.post("/run/python", json={"script": "print('Hello')"}, headers=auth_headers)
        assert response.status_code == 200

def test_inspect_window_requires_target(auth_headers):
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.post("/inspect/window", json={}, headers=auth_headers)
        assert response.status_code == 400

@patch("subprocess.run")
@patch("builtins.open", new_callable=MagicMock)
@patch("os.path.exists")
def test_inspect_window_list_only(mock_exists, mock_open, mock_run, auth_headers):
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        mock_exists.return_value = True
        mock_run.return_value.returncode = 0
        mock_open.return_value.__enter__.return_value.read.return_value = '{"windows":[]}'
        response = client.post("/inspect/window", json={"list_only": True}, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "success"
