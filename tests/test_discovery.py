import os
from unittest.mock import MagicMock, mock_open, patch

import pytest
from zeroconf import ServiceStateChange

from api.core.discovery import SERVICE_TYPE, DiscoveryManager


@pytest.fixture
def discovery_manager():
    with patch.dict(
        os.environ,
        {
            "WINEBOT_SESSION_ID": "test-session",
            "ALLOW_MULTIPLE_SESSIONS": "True",
            "API_PORT": "8000",
            "NOVNC_PORT": "6080",
        },
    ):
        return DiscoveryManager()


def test_init(discovery_manager):
    assert discovery_manager.session_id == "test-session"
    assert discovery_manager.allow_multiple is True
    assert discovery_manager.api_port == 8000
    assert discovery_manager.vnc_port == 6080


@patch("socket.socket")
def test_get_ip(mock_socket_cls, discovery_manager):
    mock_socket = MagicMock()
    mock_socket_cls.return_value = mock_socket
    mock_socket.getsockname.return_value = ["192.168.1.100"]

    ip = discovery_manager._get_ip()
    assert ip == "192.168.1.100"


@patch("os.listdir")
def test_list_active_exes(mock_listdir, discovery_manager):
    mock_listdir.return_value = ["123", "456", "not_a_pid"]

    def open_side_effect(file, mode):
        if file == "/proc/123/comm":
            return mock_open(read_data="notepad.exe").return_value
        elif file == "/proc/456/comm":
            return mock_open(read_data="bash").return_value
        raise FileNotFoundError

    with patch("builtins.open", side_effect=open_side_effect):
        exes = discovery_manager._list_active_exes()
        assert "notepad.exe" in exes
        assert "bash" not in exes


@patch("api.core.discovery.Zeroconf")
@patch("api.core.discovery.ServiceInfo")
def test_start_internal(mock_service_info, mock_zeroconf_cls, discovery_manager):
    mock_zeroconf = MagicMock()
    mock_zeroconf_cls.return_value = mock_zeroconf
    # Mock get_service_info to return None (no collision)
    mock_zeroconf.get_service_info.return_value = None

    with patch.object(discovery_manager, "_get_ip", return_value="1.2.3.4"):
        discovery_manager._start_internal()

    mock_zeroconf.register_service.assert_called_once()
    mock_service_info.assert_called()
    args, kwargs = mock_service_info.call_args
    assert args[0] == SERVICE_TYPE
    assert "WineBot-Session-test-session" in args[1]
    assert kwargs["port"] == 8000


@patch("api.core.discovery.Zeroconf")
@patch("os._exit")
def test_singleton_check_fail(mock_exit, mock_zeroconf_cls):
    # Setup environment to disallow multiple sessions
    with patch.dict(os.environ, {"ALLOW_MULTIPLE_SESSIONS": "False"}):
        dm = DiscoveryManager()

        # Mock Zeroconf and ServiceBrowser behavior
        mock_zeroconf = MagicMock()
        mock_zeroconf_cls.return_value = mock_zeroconf

        # We need to simulate the ServiceBrowser finding a service.
        # implementation of _check_singleton uses a callback.
        # Since we mock Zeroconf and ServiceBrowser, the callback won't be called automatically.
        # We need to manually invoke the callback passed to ServiceBrowser.

        with patch("api.core.discovery.ServiceBrowser") as mock_browser_cls:
            # We want to trigger the found_other = True logic.
            # But the callback is defined inside _check_singleton.
            # So we have to patch ServiceBrowser to capture the callback and call it.

            def side_effect(zc, type_, handlers):
                # Simulate finding a service
                handlers[0](
                    zc, type_, "ExistingSession", ServiceStateChange.Added
                )  # 1 = Added
                return MagicMock()

            mock_browser_cls.side_effect = side_effect

            dm._check_singleton()

            mock_exit.assert_called_with(1)


@patch("api.core.discovery.Zeroconf")
@patch("os._exit")
def test_singleton_check_pass(mock_exit, mock_zeroconf_cls):
    with patch.dict(os.environ, {"ALLOW_MULTIPLE_SESSIONS": "False"}):
        dm = DiscoveryManager()

        with patch("api.core.discovery.ServiceBrowser"):
            # No service found
            dm._check_singleton()

            mock_exit.assert_not_called()
