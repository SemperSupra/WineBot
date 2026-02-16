import socket
import threading
import time
import json
import datetime
import os
import signal
import sys
from typing import Dict, Tuple, Any

try:
    from api.core.versioning import EVENT_SCHEMA_VERSION
except ImportError:
    EVENT_SCHEMA_VERSION = "1.0"


def dlog(msg: str) -> None:
    print(f"[{datetime.datetime.now().isoformat()}] {msg}")


class VNCInputProxy:
    def __init__(
        self,
        listen_host: str,
        listen_port: int,
        target_host: str,
        target_port: int,
        session_dir: str,
        sample_motion_ms: int = 0,
    ):
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.target_host = target_host
        self.target_port = target_port
        self.session_dir = session_dir
        self.sample_motion_ms = sample_motion_ms
        self.log_path = os.path.join(session_dir, "logs", "input_events_network.jsonl")
        self.stop_requested = False
        self.buffer = b""
        self.last_motion_ts: float = 0.0
        self.seq = 0

        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

    def run(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((self.listen_host, self.listen_port))
        server_sock.listen(5)
        dlog(f"VNC Proxy listening on {self.listen_host}:{self.listen_port}")

        while not self.stop_requested:
            try:
                server_sock.settimeout(1.0)
                client_sock, addr = server_sock.accept()
                dlog(f"Accepted connection from {addr}")
                threading.Thread(
                    target=self.handle_client, args=(client_sock, addr), daemon=True
                ).start()
            except socket.timeout:
                continue
            except Exception as e:
                if not self.stop_requested:
                    dlog(f"Accept error: {e}")

    def handle_client(self, client_sock, client_addr):
        try:
            target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_sock.connect((self.target_host, self.target_port))
        except Exception as e:
            dlog(
                f"Failed to connect to target {self.target_host}:{self.target_port}: {e}"
            )
            client_sock.close()
            return

        stop_flag = {"stop": False}
        t1 = threading.Thread(
            target=self.proxy_data,
            args=(client_sock, target_sock, "c2s", stop_flag, client_addr),
        )
        t2 = threading.Thread(
            target=self.proxy_data,
            args=(target_sock, client_sock, "s2c", stop_flag, client_addr),
        )
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        client_sock.close()
        target_sock.close()

    def proxy_data(self, source, dest, direction, stop_flag, client_addr):
        try:
            while not stop_flag["stop"] and not self.stop_requested:
                source.settimeout(1.0)
                try:
                    data = source.recv(4096)
                except socket.timeout:
                    continue
                if not data:
                    break

                if direction == "c2s":
                    self.parse_client_data(data, client_addr)

                dest.sendall(data)
        except Exception as e:
            if not stop_flag["stop"]:
                dlog(f"Proxy error ({direction}): {e}")
        finally:
            stop_flag["stop"] = True

    def parse_client_data(self, data: bytes, client_addr: Tuple[str, int]):
        self.buffer += data
        try:
            while len(self.buffer) > 0:
                msg_type = self.buffer[0]
                if msg_type == 0:  # SetPixelFormat
                    if len(self.buffer) < 20:
                        return
                    self.buffer = self.buffer[20:]
                    continue
                if msg_type == 2:  # SetEncodings
                    if len(self.buffer) < 4:
                        return
                    count = int.from_bytes(self.buffer[2:4], "big")
                    total = 4 + (count * 4)
                    if len(self.buffer) < total:
                        return
                    self.buffer = self.buffer[total:]
                    continue
                if msg_type == 3:  # FramebufferUpdateRequest
                    if len(self.buffer) < 10:
                        return
                    self.buffer = self.buffer[10:]
                    continue
                if msg_type == 4:  # KeyEvent
                    if len(self.buffer) < 8:
                        return
                    down = self.buffer[1] == 1
                    key = int.from_bytes(self.buffer[4:8], "big")
                    self.buffer = self.buffer[8:]
                    self.emit_event("key", {"down": down, "key": key}, client_addr)
                    continue
                if msg_type == 5:  # PointerEvent
                    if len(self.buffer) < 6:
                        return
                    button_mask = self.buffer[1]
                    x = int.from_bytes(self.buffer[2:4], "big")
                    y = int.from_bytes(self.buffer[4:6], "big")
                    self.buffer = self.buffer[6:]
                    self.emit_event(
                        "pointer",
                        {"button_mask": button_mask, "x": x, "y": y},
                        client_addr,
                    )
                    continue
                if msg_type == 6:  # ClientCutText
                    if len(self.buffer) < 8:
                        return
                    length = int.from_bytes(self.buffer[4:8], "big")
                    total = 8 + length
                    if len(self.buffer) < total:
                        return
                    self.buffer = self.buffer[total:]
                    continue

                # RFB Handshake handling (Security types etc)
                if self.buffer.startswith(b"RFB "):
                    idx = self.buffer.find(b"\n")
                    if idx == -1:
                        return
                    self.buffer = self.buffer[idx + 1 :]
                    continue

                # Fallback: Discard one byte if unknown
                self.buffer = self.buffer[1:]
        except Exception as e:
            dlog(f"Parser error: {e}")

    def emit_event(self, kind: str, data: Dict[str, Any], client_addr: Tuple[str, int]):
        if kind == "pointer" and self.sample_motion_ms > 0:
            now = time.time() * 1000
            if now - self.last_motion_ts < self.sample_motion_ms:
                return
            self.last_motion_ts = now

        payload = {
            "schema_version": EVENT_SCHEMA_VERSION,
            "timestamp_epoch_ms": int(time.time() * 1000),
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "session_id": os.path.basename(self.session_dir),
            "source": "network",
            "layer": "network",
            "origin": "user",
            "tool": "vnc-proxy",
            "client": f"{client_addr[0]}:{client_addr[1]}",
            "event": f"vnc_{kind}",
            "seq": self.seq,
        }
        self.seq += 1
        payload.update(data)

        with open(self.log_path, "a") as f:
            f.write(json.dumps(payload) + "\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--target-port", type=int, required=True)
    parser.add_argument("--session-dir", required=True)
    parser.add_argument("--sample-motion-ms", type=int, default=0)
    args = parser.parse_args()

    proxy = VNCInputProxy(
        "0.0.0.0",
        args.listen_port,
        "127.0.0.1",
        args.target_port,
        args.session_dir,
        args.sample_motion_ms,
    )

    def handle_sigterm(sig, frame):
        proxy.stop_requested = True
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)
    proxy.run()
