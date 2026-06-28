import socket

import requests


def check_port(host, port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((host, port))
        s.close()
        print(f"[OK] Port {port} is open.")
        return True
    except Exception as e:
        print(f"[FAIL] Port {port} is closed/unreachable: {e}")
        return False


def check_http(url):
    try:
        r = requests.get(url, timeout=2)
        if r.status_code == 200:
            print(f"[OK] {url} returned 200.")
            return True
        else:
            print(f"[FAIL] {url} returned {r.status_code}.")
            return False
    except Exception as e:
        print(f"[FAIL] {url} request failed: {e}")
        return False


def main():
    print("--- Diagnostic: Connectivity ---")

    # 1. Check VNC Port (5900)
    check_port("localhost", 5900)

    # 2. Check noVNC Port (6080)
    novnc_port_ok = check_port("localhost", 6080)

    # 3. Check API Port (8000)
    api_port_ok = check_port("localhost", 8000)

    if not novnc_port_ok:
        print("\nSkipping HTTP checks for 6080 because port is closed.")
    else:
        # 4. Check noVNC Static File (Standalone)
        check_http("http://localhost:6080/vnc.html")

    if not api_port_ok:
        print("\nSkipping HTTP checks for 8000 because port is closed.")
    else:
        # 5. Check Dashboard Static File (rfb.js)
        check_http("http://localhost:8000/ui/core/rfb.js")
        check_http("http://localhost:8000/ui/core/util/int.js")

        # 6. Check Dashboard Index
        check_http("http://localhost:8000/ui/")


if __name__ == "__main__":
    main()
