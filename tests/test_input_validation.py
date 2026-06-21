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


class TestXDotoolToAHKKeys:
    """Unit tests for xdotool-to-AHK key syntax translation."""

    def test_modifier_chord_ctrl(self):
        from api.routers.input import _xdotool_to_ahk_keys
        assert _xdotool_to_ahk_keys("ctrl+c") == "^c"

    def test_modifier_chord_alt(self):
        from api.routers.input import _xdotool_to_ahk_keys
        assert _xdotool_to_ahk_keys("alt+F4") == "!{F4}"

    def test_modifier_chord_ctrl_shift(self):
        from api.routers.input import _xdotool_to_ahk_keys
        assert _xdotool_to_ahk_keys("ctrl+shift+a") == "^+a"

    def test_modifier_chord_super(self):
        from api.routers.input import _xdotool_to_ahk_keys
        result = _xdotool_to_ahk_keys("super+r")
        assert result == "#r" or result == "#r"

    def test_named_key_return(self):
        from api.routers.input import _xdotool_to_ahk_keys
        assert _xdotool_to_ahk_keys("Return") == "{Enter}"

    def test_named_key_escape(self):
        from api.routers.input import _xdotool_to_ahk_keys
        assert _xdotool_to_ahk_keys("Escape") == "{Esc}"

    def test_named_key_tab(self):
        from api.routers.input import _xdotool_to_ahk_keys
        assert _xdotool_to_ahk_keys("Tab") == "{Tab}"

    def test_named_key_backspace(self):
        from api.routers.input import _xdotool_to_ahk_keys
        assert _xdotool_to_ahk_keys("BackSpace") == "{BS}"

    def test_named_key_space(self):
        from api.routers.input import _xdotool_to_ahk_keys
        assert _xdotool_to_ahk_keys("space") == "{Space}"

    def test_named_key_delete(self):
        from api.routers.input import _xdotool_to_ahk_keys
        assert _xdotool_to_ahk_keys("Delete") == "{Delete}"

    def test_function_key(self):
        from api.routers.input import _xdotool_to_ahk_keys
        assert _xdotool_to_ahk_keys("F5") == "{F5}"

    def test_function_key_f12(self):
        from api.routers.input import _xdotool_to_ahk_keys
        assert _xdotool_to_ahk_keys("F12") == "{F12}"

    def test_arrow_keys(self):
        from api.routers.input import _xdotool_to_ahk_keys
        assert _xdotool_to_ahk_keys("Up") == "{Up}"
        assert _xdotool_to_ahk_keys("Down") == "{Down}"
        assert _xdotool_to_ahk_keys("Left") == "{Left}"
        assert _xdotool_to_ahk_keys("Right") == "{Right}"

    def test_plain_text(self):
        from api.routers.input import _xdotool_to_ahk_keys
        assert _xdotool_to_ahk_keys("Hello") == "Hello"

    def test_plain_text_with_spaces(self):
        from api.routers.input import _xdotool_to_ahk_keys
        assert _xdotool_to_ahk_keys("Hello World")

    def test_single_character(self):
        from api.routers.input import _xdotool_to_ahk_keys
        result = _xdotool_to_ahk_keys("a")
        assert result == "a"

    def test_empty_string_raises(self):
        from api.routers.input import _xdotool_to_ahk_keys
        import pytest
        with pytest.raises(ValueError):
            _xdotool_to_ahk_keys("")

    def test_whitespace_only_raises(self):
        from api.routers.input import _xdotool_to_ahk_keys
        import pytest
        with pytest.raises(ValueError):
            _xdotool_to_ahk_keys("   ")

    def test_ahk_special_chars_escaped(self):
        from api.routers.input import _xdotool_to_ahk_keys
        # Raw +, ^, !, #, % should be escaped in plain-text mode
        result = _xdotool_to_ahk_keys("+")
        assert "{+}" in result
        result = _xdotool_to_ahk_keys("^")
        assert "{^}" in result
        result = _xdotool_to_ahk_keys("%")
        assert "`%" in result, f"Expected backtick-escaped %, got: {result!r}"
        result = _xdotool_to_ahk_keys("%%DATE%%")
        assert "`%" in result, f"Expected % escaped, got: {result!r}"

    def test_ctrl_alt_delete_chord(self):
        from api.routers.input import _xdotool_to_ahk_keys
        result = _xdotool_to_ahk_keys("ctrl+alt+Delete")
        assert result == "^!{Delete}"
