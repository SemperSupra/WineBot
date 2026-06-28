import asyncio
import sys

import websockets


async def test_ws(uri):
    print(f"Testing {uri}...")
    try:
        async with websockets.connect(uri, subprotocols=["binary"]):
            print(f"[OK] Connected to {uri}")
            return True
    except Exception as e:
        print(f"[FAIL] {uri}: {e}")
        return False


async def main():
    print("--- Diagnostic: WebSocket ---")
    root_ok = await test_ws("ws://localhost:6080/")
    path_ok = await test_ws("ws://localhost:6080/websockify")

    if not root_ok and not path_ok:
        print("Both failed.")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ImportError:
        print("websockets module not found. Please install it.")
        sys.exit(1)
