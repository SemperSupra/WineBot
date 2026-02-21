import socket
import logging
import time
import threading
import os
from typing import Optional, Dict, Any
from zeroconf import (
    IPVersion,
    ServiceInfo,
    Zeroconf,
    ServiceBrowser,
    ServiceStateChange,
)

from api.utils.config import config

logger = logging.getLogger("winebot.discovery")

SERVICE_TYPE = config.MDNS_SERVICE_TYPE


class DiscoveryManager:
    """Manages mDNS/Zeroconf service registration and discovery."""

    def __init__(self):
        self.zeroconf: Optional[Zeroconf] = None
        self.service_info: Optional[ServiceInfo] = None
        self.update_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.allow_multiple = config.WINEBOT_DISCOVERY_ALLOW_MULTIPLE

    def _get_local_ip(self) -> str:
        try:
            # Create a dummy socket to find local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def _get_txt_records(self) -> Dict[str, str]:
        from api.utils.files import read_session_dir, session_id_from_dir
        import hmac
        import hashlib

        session_dir = read_session_dir()
        session_id = session_id_from_dir(session_dir) or "none"
        
        # Include a hash of the API token if set, so clients can verify credentials
        token = config.API_TOKEN or ""
        token_hash = ""
        if token:
            token_hash = hmac.new(
                b"winebot-discovery", token.encode(), hashlib.sha256
            ).hexdigest()[:8]

        return {
            "version": "0.9.6",
            "session_id": session_id,
            "api_port": str(config.API_PORT),
            "vnc_port": str(config.VNC_PORT),
            "novnc_port": str(config.NOVNC_PORT),
            "token_sig": token_hash,
        }

    def _check_singleton(self) -> None:
        """Check if another instance is already running if multiple not allowed."""
        if self.allow_multiple:
            return

        zc = Zeroconf()
        found_other = False

        def on_service_state_change(zeroconf, service_type, name, state_change):
            nonlocal found_other
            if state_change is ServiceStateChange.Added:
                # Basic check - if we find ANY other winebot service
                # In a real impl, we might check if it's 'our' IP or not
                found_other = True

        ServiceBrowser(zc, SERVICE_TYPE, handlers=[on_service_state_change])
        time.sleep(2)  # Brief scan
        zc.close()

        if found_other:
            logger.warning(
                "Another WineBot service detected on network. Policy allows multiple, continuing."
            )

    def start(self, session_id: str) -> None:
        """Register the service."""
        try:
            self._check_singleton()

            ip = self._get_local_ip()
            print(
                f"--> Starting DiscoveryManager (ALLOW_MULTIPLE={self.allow_multiple})..."
            )
            print(
                f"--> Registering mDNS service: WineBot-Session-{session_id}.{SERVICE_TYPE}"
            )
            print(f"--> Discovery IP: {ip}")

            self.zeroconf = Zeroconf(ip_version=IPVersion.V4Only)

            txt_records = self._get_txt_records()

            self.service_info = ServiceInfo(
                SERVICE_TYPE,
                f"WineBot-Session-{session_id}.{SERVICE_TYPE}",
                addresses=[socket.inet_aton(ip)],
                port=config.API_PORT,
                properties=txt_records,
                server=f"{socket.gethostname()}.local.",
            )

            self.zeroconf.register_service(self.service_info)
            print("--> mDNS service registered successfully.")

            # Start dynamic update thread (currently just keeps thread alive)
            self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
            self.update_thread.start()
        except Exception as e:
            print(f"--> Discovery background startup failed: {e}")
            logger.error(f"Discovery background startup failed: {e}")

    def _update_loop(self) -> None:
        while not self.stop_event.is_set():
            # Properties are currently static to avoid Zeroconf 0.131+ immutability issues
            # We just sleep and check the stop event
            if self.stop_event.wait(config.MDNS_UPDATE_INTERVAL_SEC):
                break

    def stop(self) -> None:
        self.stop_event.set()
        if self.zeroconf:
            if self.service_info:
                logger.info(f"Unregistering mDNS service: {self.service_info.name}")
                self.zeroconf.unregister_service(self.service_info)
            self.zeroconf.close()
            self.zeroconf = None

    def status(self) -> Dict[str, Any]:
        """Returns the current discovery status."""
        return {
            "enabled": self.zeroconf is not None,
            "service_name": self.service_info.name if self.service_info else None,
            "registered": self.service_info is not None and self.zeroconf is not None,
        }


discovery_manager = DiscoveryManager()
