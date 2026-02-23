from fastapi.testclient import TestClient
from api.server import app
from unittest.mock import patch, MagicMock
import os
import pytest

client = TestClient(app)


@pytest.fixture
def auth_headers():
    return {"X-API-Key": "test-token"}


@patch("api.routers.input.broker.check_access", return_value=True)
@patch("api.routers.input._require_active_session", return_value="/tmp/session")
@patch("api.routers.input.append_input_event")
@patch("api.routers.input.run_async_command", new_callable=MagicMock)
def test_click_at_validation(
    mock_run_async, mock_append, mock_session, mock_broker, auth_headers
):
    # Setup AsyncMock return value
    async def async_return(*args, **kwargs):
        return {"ok": True, "stdout": "12345", "stderr": ""}

    mock_run_async.side_effect = async_return

    # Mock screen resolution to 1280x720
    with patch.dict(os.environ, {"API_TOKEN": "test-token", "SCREEN": "1280x720x24"}):
        # 1. Valid click
        response = client.post(
            "/input/mouse/click", json={"x": 100, "y": 100}, headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["status"] == "clicked"

        # 2. Out of bounds click (x)
        response = client.post(
            "/input/mouse/click", json={"x": 1300, "y": 100}, headers=auth_headers
        )
        assert response.status_code == 400
        assert "out of bounds" in response.json()["detail"]

        # 3. Out of bounds click (y)
        response = client.post(
            "/input/mouse/click", json={"x": 100, "y": 800}, headers=auth_headers
        )
        assert response.status_code == 400
        assert "out of bounds" in response.json()["detail"]

        # 4. Relative click (should bypass bounds check)
        response = client.post(
            "/input/mouse/click",
            json={"x": 2000, "y": 2000, "relative": True, "window_title": "Notepad"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "clicked"
