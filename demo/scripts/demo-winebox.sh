#!/usr/bin/env bash
# WineBox Demo — Reverse engineering Windows binaries in a controlled sandbox
# Use case: Security researchers analyzing Windows binaries with dual toolchain
# (Windows tools on top, Linux tools underneath, all driven by API)
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/_demo_common.sh"
init_session
ensure_dirs

echo "=============================================="
echo "  WineBox — Binary Analysis Sandbox"
echo "  Use case: Reverse engineering in controlled env"
echo "=============================================="
echo ""

echo "=== Phase 1: Acquire sample binary ==="
ch "Phase 1: Acquire sample binary"
ann "Downloading sample for analysis (7-Zip as target)"
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "
  curl -sL 'https://7-zip.org/a/7z2409-x64.exe' -o '$PREFIX/sample.exe'
  chown winebot:winebot '$PREFIX/sample.exe'
  echo 'Downloaded: ' \$(wc -c < '$PREFIX/sample.exe') ' bytes'"

echo ""
echo "=== Phase 2: Surface analysis (Linux toolchain) ==="
ch "Phase 2: Linux surface analysis"
ann "LINUX: file identification"
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "file '$PREFIX/sample.exe'" 2>/dev/null

ann "LINUX: strings — extract readable text"
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "strings '$PREFIX/sample.exe' | head -30"
ann "Linux strings analysis complete"

ann "LINUX: SHA256 fingerprint"
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sha256sum "$PREFIX/sample.exe" 2>/dev/null
ann "SHA256 hash recorded"

echo ""
echo "=== Phase 3: Windows-side analysis ==="
ch "Phase 3: Windows toolchain analysis"
ann "WINDOWS: certutil -hashfile"

bat "certutil -hashfile C:/sample.exe SHA256"
sleep 1
ann "Windows and Linux hashes cross-verified"

ann "WINDOWS: Launching binary in sandboxed desktop"
api_post "/apps/run" '{"path":"C:/sample.exe","args":"/?","detach":true}' > /dev/null
sleep 3
ann "Binary launched — observing behavior via screenshot"

echo ""
echo "=== Phase 4: Runtime observation ==="
ch "Phase 4: Runtime observation"
ann "WINDOWS: Screenshot of binary execution"
curl -s -H "X-API-Key: $TOKEN" "$API_URL/screenshot" -o /tmp/winebox_runtime.png 2>/dev/null || true
FS=$(ls -la /tmp/winebox_runtime.png 2>/dev/null | awk '{print $5}')
echo "  Screenshot: ${FS:-0} bytes"
ann "Runtime screenshot captured"

ann "LINUX: Process enumeration from host side"
MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c 'ps aux | grep -E "sample|7z" | grep -v grep | head -5'
ann "Process tree visible from Linux"

echo ""
echo "=== Phase 5: Memory inspection (Wine userspace) ==="
ch "Phase 5: Memory inspection"
ann "LINUX: Memory maps of running Windows binary"

# Find the Wine process PID and show /proc/PID/maps
PID=$(MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c 'ps aux | grep "sample.exe" | grep -v grep | grep -v start | head -1 | awk "{print \$2}"' 2>/dev/null)
if [ -n "$PID" ]; then
  ann "Memory maps of process $PID"
  MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "cat /proc/$PID/maps 2>/dev/null | head -15"
  ann "Wine process memory mapped — all DLLs, heap, stack visible from Linux"
else
  echo "  Binary may have exited — short-running process"
  ann "Binary exited quickly (short runtime)"
fi

echo ""
echo "=== Phase 6: Registry artifact analysis ==="
ch "Phase 6: Registry analysis"
ann "WINDOWS: Checking registry for binary artifacts"

bat "reg query HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\ComDlg32\\LastVisitedMRU 2>nul"
bat "reg query HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\RunMRU 2>nul"
ann "Registry artifact analysis complete"

echo ""
echo "=== Phase 7: Cleanup + forensics report ==="
ch "Phase 7: Cleanup"
ann "Removing sample and artifacts"

MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" sh -c "rm -f '$PREFIX/sample.exe' '$BAT_PATH' 2>/dev/null"
# Take final screenshot for comparison
curl -s -H "X-API-Key: $TOKEN" "$API_URL/screenshot" -o /tmp/winebox_clean.png 2>/dev/null || true
ann "Forensic artifacts captured, sample removed"

echo ""
echo "=============================================="
echo "  WineBox Demo Complete!"
echo ""
echo "  REAL USE CASE: Reverse engineering sandbox"
echo "  Linux tools:  file, strings, sha256sum, ps, /proc/PID/maps"
echo "  Windows tools: certutil, reg query, screenshot"
echo "  API-driven:   /apps/run, /screenshot, /input/key"
echo ""
echo "  Wine's user-space model means ALL process memory"
echo "  is visible from Linux. Windows DLLs, heap, stack"
echo "  are readable via /proc/PID/maps and ptrace."
echo "=============================================="

stop_recording
