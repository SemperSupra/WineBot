from fastapi.testclient import TestClient
from api.server import app
from unittest.mock import patch, MagicMock
import os
import pytest

client = TestClient(app)

# Helper to mock token
@pytest.fixture
def auth_headers():
    return {"X-API-Key": "test-token"}

@patch("subprocess.run")
def test_health_check(mock_run, auth_headers):
    # Mock env var
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        mock_run.return_value.returncode = 0
        response = client.get("/health", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "x11": "connected"}
        mock_run.assert_called_with(["xdpyinfo"], check=True, capture_output=True)

@patch("subprocess.run")
def test_health_check_unauthorized(mock_run):
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.get("/health", headers={"X-API-Key": "wrong"})
        assert response.status_code == 403

@patch("subprocess.run")
def test_health_check_no_token_required(mock_run):
    # No API_TOKEN env var set
    with patch.dict(os.environ, {}, clear=True):
        mock_run.return_value.returncode = 0
        response = client.get("/health") # No header
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
