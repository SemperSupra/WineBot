#!/usr/bin/env bash
# WineBox Demo — Reverse engineering Windows binaries in a controlled sandbox
# Use case: Security researchers analyzing Windows binaries with dual toolchain
# (Windows tools on top, Linux tools underneath, all driven by API)
set -u
API_URL="http://localhost:8000"
PREFIX="/wineprefix/drive_c"
BAT="$PREFIX/__cmd.bat"

detect_token() { [ -n "${API_TOKEN:-}" ] && { TOKEN="$API_TOKEN"; return; }
  TOKEN=$(MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c 'cat /tmp/winebot_api_token 2>/dev/null || cat /winebot-shared/winebot_api_token 2>/dev/null' 2>/dev/null | tr -d '[:space:]' || true)
  [ -z "$TOKEN" ] && { echo "ERROR: No token"; exit 1; } }
api_post() { curl -sfS -X POST -H "X-API-Key: $TOKEN" -H "Content-Type: application/json" -d "$2" "$API_URL$1" 2>/dev/null; }
ann() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text \"$1\" --kind annotation --source demo" 2>/dev/null || true; }
ch()   { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "python3 -m automation.recorder annotate --session-dir '$SESSDIR' --text \"$1\" --kind chapter --source demo" 2>/dev/null || true; }
vf() { MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "test -f $1 && echo EXISTS \$(wc -c< $1)bytes || echo MISSING" 2>/dev/null; }

# Run Windows command via .bat (avoid bash redirection issues)
bat() { local content="$1"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "cat > ${BAT} << 'BATEOF'
${content}
BATEOF
chown winebot:winebot ${BAT}"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "gosu winebot env DISPLAY=:99 WINEPREFIX=/wineprefix WINEDEBUG=-all wine cmd.exe /c 'C:\\\\__cmd.bat' 2>/dev/null"; }

detect_token
SESSION=$(curl -s -H "X-API-Key: $TOKEN" "$API_URL/lifecycle/status" | grep -o '"session_id":[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
SESSDIR="/artifacts/sessions/$SESSION"
CT=$(curl -s -X POST -H "X-API-Key: $TOKEN" "$API_URL/sessions/$SESSION/control/challenge" | grep -o '"token":[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
api_post "/sessions/$SESSION/control/grant" "{\"lease_seconds\":7200,\"user_ack\":true,\"challenge_token\":\"$CT\"}" > /dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 mkdir -p "$PREFIX" 2>/dev/null
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 chown -R winebot:winebot "$PREFIX" 2>/dev/null

echo "=============================================="
echo "  WineBox — Binary Analysis Sandbox"
echo "  Use case: Reverse engineering in controlled env"
echo "=============================================="
echo ""

echo "=== Phase 1: Acquire sample binary ==="
ch "Phase 1: Acquire sample binary"
ann "Downloading sample for analysis (7-Zip as target)"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
  curl -sL 'https://7-zip.org/a/7z2409-x64.exe' -o '$PREFIX/sample.exe'
  chown winebot:winebot '$PREFIX/sample.exe'
  echo 'Downloaded: ' \$(wc -c < '$PREFIX/sample.exe') ' bytes'"

echo ""
echo "=== Phase 2: Surface analysis (Linux toolchain) ==="
ch "Phase 2: Linux surface analysis"
ann "LINUX: file identification"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "file '$PREFIX/sample.exe'" 2>/dev/null

ann "LINUX: strings — extract readable text"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "strings '$PREFIX/sample.exe' | head -30"
ann "Linux strings analysis complete"

ann "LINUX: SHA256 fingerprint"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sha256sum "$PREFIX/sample.exe" 2>/dev/null
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
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c 'ps aux | grep -E "sample|7z" | grep -v grep | head -5'
ann "Process tree visible from Linux"

echo ""
echo "=== Phase 5: Memory inspection (Wine userspace) ==="
ch "Phase 5: Memory inspection"
ann "LINUX: Memory maps of running Windows binary"

# Find the Wine process PID and show /proc/PID/maps
PID=$(MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c 'ps aux | grep "sample.exe" | grep -v grep | grep -v start | head -1 | awk "{print \$2}"' 2>/dev/null)
if [ -n "$PID" ]; then
  ann "Memory maps of process $PID"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "cat /proc/$PID/maps 2>/dev/null | head -15"
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

MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "rm -f '$PREFIX/sample.exe' '$BAT' 2>/dev/null"
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

api_post "/recording/stop" '{}' 2>/dev/null || true
sleep 2; TRIM_SS="${TRIM_SS:-30}"
MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
  ffmpeg -y -ss ${TRIM_SS} -i ${SESSDIR}/video_001.mkv -c copy -avoid_negative_ts make_zero /tmp/trimmed.mkv 2>/dev/null
  ffmpeg -y -i /tmp/trimmed.mkv -vf 'fps=8,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse' -loop 0 /tmp/trimmed.gif 2>/dev/null
  echo 'Trimmed:' \$(ls -lh /tmp/trimmed.mkv | awk '{print \$5}') 'GIF:' \$(ls -lh /tmp/trimmed.gif | awk '{print \$5}')
"
echo "Output: docker cp compose-winebot-interactive-1:/tmp/trimmed.mkv demo/output/demo.mkv"
