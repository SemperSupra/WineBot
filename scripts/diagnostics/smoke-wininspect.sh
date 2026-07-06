#!/usr/bin/env bash
# EXECUTION: IN_CONTAINER - verifies bundled WinInspect daemon and CLI under Wine
# STATUS: ACTIVE - release smoke for WinInspect integration
set -euo pipefail

LOG_DIR="${1:-/artifacts/diagnostics_master/wininspect}"
mkdir -p "$LOG_DIR"

find_wininspect_dir() {
    for dir in \
        "/opt/winebot/windows-tools/WinSpy" \
        "/opt/winebot/windows-tools/WinInspect" \
        "$HOME/windows-tools/WinSpy" \
        "$HOME/windows-tools/WinInspect"; do
        if [ -f "$dir/wininspect.exe" ] && [ -f "$dir/wininspectd.exe" ]; then
            printf '%s\n' "$dir"
            return 0
        fi
    done
    return 1
}

if ! WININSPECT_DIR="$(find_wininspect_dir)"; then
    echo "WinInspect smoke: wininspect.exe and wininspectd.exe not found." >&2
    exit 1
fi

CLI="$WININSPECT_DIR/wininspect.exe"
DAEMON="$WININSPECT_DIR/wininspectd.exe"
GUI="$WININSPECT_DIR/wininspect-gui.exe"

echo "WinInspect smoke: using $WININSPECT_DIR"

if [ ! -f "$GUI" ]; then
    echo "WinInspect smoke: warning: wininspect-gui.exe not found." >&2
fi

wine "$CLI" --help > "$LOG_DIR/cli-help.log" 2>&1 || {
    echo "WinInspect smoke: CLI --help failed." >&2
    tail -n 80 "$LOG_DIR/cli-help.log" >&2 || true
    exit 1
}

wine "$DAEMON" --help > "$LOG_DIR/daemon-help.log" 2>&1 || {
    echo "WinInspect smoke: daemon --help failed." >&2
    tail -n 80 "$LOG_DIR/daemon-help.log" >&2 || true
    exit 1
}

wine "$DAEMON" > "$LOG_DIR/daemon.log" 2>&1 &
daemon_pid=$!

cleanup() {
    if kill -0 "$daemon_pid" 2>/dev/null; then
        kill "$daemon_pid" 2>/dev/null || true
        wait "$daemon_pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT

python3 - <<'PY'
import socket
import sys
import time

deadline = time.monotonic() + 30
while time.monotonic() < deadline:
    try:
        with socket.create_connection(("127.0.0.1", 1985), timeout=1):
            sys.exit(0)
    except OSError:
        time.sleep(0.5)
sys.exit("WinInspect daemon did not open TCP 127.0.0.1:1985 within 30s")
PY

wine "$CLI" capabilities > "$LOG_DIR/capabilities.json" 2> "$LOG_DIR/capabilities.err" || {
    echo "WinInspect smoke: capabilities command failed." >&2
    tail -n 80 "$LOG_DIR/capabilities.err" >&2 || true
    tail -n 80 "$LOG_DIR/daemon.log" >&2 || true
    exit 1
}

wine "$CLI" top > "$LOG_DIR/top.json" 2> "$LOG_DIR/top.err" || {
    echo "WinInspect smoke: top command failed." >&2
    tail -n 80 "$LOG_DIR/top.err" >&2 || true
    tail -n 80 "$LOG_DIR/daemon.log" >&2 || true
    exit 1
}

python3 - "$LOG_DIR/capabilities.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8", errors="replace").strip()
if not text:
    sys.exit("WinInspect capabilities output is empty")
try:
    payload = json.loads(text)
except json.JSONDecodeError:
    # Some CLI versions may print a human-readable wrapper. Keep the smoke
    # useful by requiring at least capability keywords until the CLI contract is
    # pinned in WineBot.
    required = ("clipboard", "input", "registry", "pipe")
    missing = [word for word in required if word not in text.lower()]
    if missing:
        sys.exit(f"WinInspect capabilities output is not JSON and misses {missing}")
else:
    serialized = json.dumps(payload).lower()
    missing = [word for word in ("clipboard", "input", "registry") if word not in serialized]
    if missing:
        sys.exit(f"WinInspect capabilities JSON misses expected fields: {missing}")
PY

echo "WinInspect smoke: PASSED"
