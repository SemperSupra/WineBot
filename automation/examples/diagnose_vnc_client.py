#!/usr/bin/env python3
import os
import socket
import struct
import threading
import time

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def d3des_encrypt(challenge, password):
    # VNC reverses bits of each byte in the key
    key = bytearray(8)
    pw_bytes = password
    if len(pw_bytes) > 8:
        pw_bytes = pw_bytes[:8]
    else:
        pw_bytes = pw_bytes + b"\0" * (8 - len(pw_bytes))

    for i in range(8):
        b = pw_bytes[i]
        # reverse bits
        b = ((b * 0x0802 & 0x22110) | (b * 0x8020 & 0x88440)) * 0x10101 >> 16
        key[i] = b & 0xFF

    # Use TripleDES to simulate DES if DES is missing
    try:
        if hasattr(algorithms, "DES"):
            algo = algorithms.DES(bytes(key))
        else:
            raise AttributeError
    except AttributeError:
        # Fallback to TripleDES
        algo = algorithms.TripleDES(bytes(key) * 3)

    cipher = Cipher(algo, modes.ECB(), backend=default_backend())
    encryptor = cipher.encryptor()
    return encryptor.update(challenge)


def drain_socket(sock):
    try:
        while True:
            data = sock.recv(4096)
            if not data:
                break
    except Exception:
        pass


def vnc_client(host, port, password):
    print(f"Connecting to {host}:{port}...")
    try:
        sock = socket.create_connection((host, port), timeout=5)
    except Exception as e:
        print(f"Connection failed: {e}")
        return

    try:
        # Handshake
        ver = sock.recv(12)
        print(f"Server version: {ver.strip().decode()}")
        sock.sendall(ver)

        # Security Types
        ntypes_bytes = sock.recv(1)
        if not ntypes_bytes:
            print("Connection closed at ntypes")
            return
        ntypes = ntypes_bytes[0]
        if ntypes == 0:
            print("Connection failed (0 types)")
            # Reason might follow
            reason_len = struct.unpack(">I", sock.recv(4))[0]
            reason = sock.recv(reason_len)
            print(f"Reason: {reason}")
            return

        types = sock.recv(ntypes)
        print(f"Supported security types: {list(types)}")

        if 2 in types:
            print("Selecting VNC Auth (2)")
            sock.sendall(b"\x02")
            challenge = sock.recv(16)
            if len(challenge) != 16:
                print(f"Invalid challenge length: {len(challenge)}")
                return

            response = d3des_encrypt(challenge, password.encode("latin-1"))
            sock.sendall(response)

            result = sock.recv(4)
            if len(result) != 4:
                print("Invalid auth result length")
                return
            res_val = struct.unpack(">I", result)[0]
            if res_val == 0:
                print("Authentication SUCCESS")
            else:
                print(f"Authentication FAILED: {res_val}")
                return
        elif 1 in types:
            print("Selecting None Auth (1)")
            sock.sendall(b"\x01")
            # For None auth in 3.8, result follows
            if b"3.8" in ver:
                result = sock.recv(4)
                res_val = struct.unpack(">I", result)[0]
                if res_val != 0:
                    print(f"Auth failed: {res_val}")
                    return
        else:
            print("No supported security type (need 1 or 2)")
            return

        # ClientInit (shared=1)
        sock.sendall(b"\x01")

        # ServerInit
        init_data = sock.recv(24)
        if len(init_data) < 24:
            print("Incomplete ServerInit")
            return
        (
            width,
            height,
            bpp,
            depth,
            big_endian,
            true_color,
            r_max,
            g_max,
            b_max,
            r_shift,
            g_shift,
            b_shift,
            padding,
            name_len,
        ) = struct.unpack(">HHBBBBHHHBBB3sI", init_data)
        name = sock.recv(name_len)
        print(f"Connected to desktop: {name.decode()} ({width}x{height})")

        # Start drainer
        t = threading.Thread(target=drain_socket, args=(sock,), daemon=True)
        t.start()

        # Send FramebufferUpdateRequest (Incremental=0, x=0, y=0, w=width, h=height)
        print("Sending FramebufferUpdateRequest...")
        sock.sendall(struct.pack(">BBHHHH", 3, 0, 0, 0, width, height))
        time.sleep(0.5)

        # Inject Mouse Event
        print("Injecting mouse click at 300,300")
        # Move first (Button 0)
        sock.sendall(struct.pack(">BBHH", 5, 0, 300, 300))
        time.sleep(0.1)
        # Button down (1)
        sock.sendall(struct.pack(">BBHH", 5, 1, 300, 300))
        time.sleep(0.1)
        # Button up (0)
        sock.sendall(struct.pack(">BBHH", 5, 0, 300, 300))
        time.sleep(0.1)

        print("Injecting key 'a'")
        # Key down (1), Keycode 97 (a)
        sock.sendall(struct.pack(">BBHI", 4, 1, 0, 97))
        time.sleep(0.1)
        # Key up (0)
        sock.sendall(struct.pack(">BBHI", 4, 0, 0, 97))

        print("Injection done")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        # sock.close() # Don't close immediately to let drainer run a bit?
        time.sleep(0.5)
        sock.close()


if __name__ == "__main__":
    host = os.environ.get("VNC_HOST", "127.0.0.1")
    port = int(os.environ.get("VNC_PORT", "5900"))
    password = os.environ.get("VNC_PASSWORD", "winebot")
    vnc_client(host, port, password)
