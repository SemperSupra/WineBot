#!/usr/bin/env bash
# Disposable public WineBot WinInspect read-only probe. No raw host, window,
# credential or process details may be exported from this synthetic experiment.
set -euo pipefail
test "$GITHUB_ACTIONS" = true || exit 2
cd "$(dirname "$0")/../.."
export BUILD_INTENT=rel WINEBOT_IMAGE_VERSION=uxref DOCKER_BUILD_RECORD_UPLOAD=false
export WINEBOT_INPUT_TRACE=0 WINEBOT_INPUT_TRACE_WINDOWS=0 WINEBOT_RECORD=0
export WINEBOT_TELEMETRY=0 WINEBOT_PERF_METRICS=0 WINEBOT_SUPERVISE_EXPLORER=0
export WINEBOT_ALLOW_HEADLESS_HYBRID=0
export API_TOKEN="$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
echo "::add-mask::$API_TOKEN"
cleanup() {
  docker compose -f compose/docker-compose.yml --profile headless down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT
echo "WININSPECT_IMAGE_BUILD=START"
if ! docker build --target intent-rel -f docker/Dockerfile -t winebot:uxref-rel . >/tmp/winebot-wininspect-build.log 2>&1; then
  echo "WININSPECT_IMAGE_BUILD=FAIL"
  exit 1
fi
echo "WININSPECT_IMAGE_BUILD=PASS"
docker compose -f compose/docker-compose.yml --profile headless up -d --no-build winebot >/dev/null
cid="$(docker compose -f compose/docker-compose.yml ps -q winebot)"
test -n "$cid" || { echo "WINEBOT_SERVICE=ABSENT"; exit 1; }
health=unknown
for _ in $(seq 1 100); do
  health="$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo absent)"
  test "$health" = healthy && break
  sleep 3
done
echo "WINEBOT_SERVICE_HEALTH=$health"
test "$health" = healthy || exit 1
docker exec -u winebot "$cid" sh -lc \
  'mkdir -p /tmp/winebot-wininspect-qual; printf "%s\n" "WinInspect synthetic Notepad fixture" > /tmp/winebot-wininspect-qual/fixture.txt'
docker exec -d -u winebot -e DISPLAY=:99 -e WINEDEBUG=-all "$cid" \
  bash -lc 'wine notepad.exe "$(winepath -w /tmp/winebot-wininspect-qual/fixture.txt)" >/tmp/winebot-wininspect-qual/notepad.log 2>&1'
visible=false
for _ in $(seq 1 25); do
  ids="$(docker exec -u winebot -e DISPLAY=:99 "$cid" xdotool search --onlyvisible --name '[Nn]otepad' 2>/dev/null || true)"
  if printf '%s\n' "$ids" | grep -Eq '^[0-9]+$'; then visible=true; break; fi
  sleep 1
done
echo "WININSPECT_SYNTHETIC_NOTEPAD_X11_VISIBLE=$visible"
docker exec -i -u winebot -e API_TOKEN="$API_TOKEN" "$cid" python3 - <<'PY'
import json, os, re, subprocess, urllib.error, urllib.request
from pathlib import Path
from api.core import wininspect as wi
def boolean(v):
    return str(bool(v)).lower()
def get(path):
    req=urllib.request.Request("http://127.0.0.1:8000"+path,
                               headers={"X-API-Key":os.environ["API_TOKEN"]})
    try:
        with urllib.request.urlopen(req, timeout=24) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as ex:
        return ex.code, None
    except Exception:
        return 0, None
default_root=Path("/opt/winebot/windows-tools/WinSpy")
nested=default_root/"App"/"WinInspect"
nested_complete=all((nested/name).is_file() for name in wi.WININSPECT_REQUIRED_FILES)
flat_complete=all((default_root/name).is_file() for name in wi.WININSPECT_REQUIRED_FILES)
print("WININSPECT_NESTED_COMPLETE="+boolean(nested_complete))
print("WININSPECT_LEGACY_FLAT_COMPLETE="+boolean(flat_complete))
print("WININSPECT_RESOLVED_COMPLETE="+boolean(wi.installed()))
x_status,windows=get("/windows")
c_status,capabilities=get("/wininspect/capabilities")
w_status,semantic=get("/wininspect/windows?include_info=false")
h_status,health=get("/health/wininspect")
print("WININSPECT_CAPABILITIES_HTTP_STATUS="+str(c_status))
print("WININSPECT_WINDOWS_HTTP_STATUS="+str(w_status))
# Only whitelisted diagnostic categories cross the public boundary. Never
# emit raw response JSON, WinInspect hello fields, window titles or exception text.
def rpc_diagnostic():
    try:
        wi.request("daemon.capabilities")
        return "rpc_success"
    except Exception as exc:
        message=str(exc).lower()
        if "e_protocol_version" in message or "expected 0.3.0" in message:
            return "protocol_version_rejected"
        if "authentication required" in message or "unauthorized" in message:
            return "rpc_unauthorized"
        if "bad method" in message or "method not implemented" in message:
            return "method_unsupported"
        if "unexpected wininspect response id" in message:
            return "response_id_mismatch"
        if "invalid wininspect json" in message or "frame too large" in message:
            return "response_framing"
        if "connection closed while reading frame" in message:
            return "connection_closed"
        if "timed out" in message or "timeout" in message:
            return "timeout"
        if "read-only mode" in message:
            return "read_only_refusal"
        return "other_redacted"
print("WININSPECT_RPC_DIAGNOSTIC="+rpc_diagnostic())
def klass(items):
    if not isinstance(items,list):return "unavailable"
    if len(items)==0:return "zero"
    if len(items)==1:return "one"
    return "two-plus"
print("X11_WINDOWS_API_OK="+boolean(x_status==200))
print("WININSPECT_CAPABILITIES_API_OK="+boolean(c_status==200))
print("WININSPECT_WINDOWS_API_OK="+boolean(w_status==200))
print("WININSPECT_HEALTH_API_OK="+boolean(h_status==200))
print("X11_WINDOW_COUNT_CLASS="+klass(windows.get("windows") if isinstance(windows,dict) else None))
print("WININSPECT_WINDOW_COUNT_CLASS="+klass(semantic.get("windows") if isinstance(semantic,dict) else None))
state=wi.ensure_daemon(start=False)
print("WININSPECT_TCP_READY="+boolean(wi._tcp_ready()))
print("WININSPECT_DAEMON_RUNNING="+boolean(state.get("running")))
def version(command):
    try:
        r=subprocess.run(command,timeout=7,capture_output=True,text=True,check=False)
        lines=r.stdout.strip().splitlines()
        value=lines[0].strip()[:100] if r.returncode==0 and lines else ""
        if re.fullmatch(r"[A-Za-z0-9.+_~:() -]{1,100}",value):
            return value.replace(" ","_")
    except Exception:
        pass
    return "unavailable"
print("WINE_EXECUTABLE_VERSION="+version(["wine","--version"]))
for package,key in (("wine","WINE_DEBIAN_VERSION"),("xvfb","XVFB_DEBIAN_VERSION"),
                    ("openbox","OPENBOX_DEBIAN_VERSION"),
                    ("libgl1-mesa-dri","MESA_DRI_VERSION"),
                    ("mesa-vulkan-drivers","MESA_VULKAN_VERSION")):
    print(key+"="+version(["dpkg-query","-W","-f=$"+"{Version}",package]))
ok=bool(wi.installed() and wi._tcp_ready() and c_status==200 and w_status==200)
print("WININSPECT_SEMANTIC_QUALIFICATION="+("PASS" if ok else "UNQUALIFIED"))
raise SystemExit(0 if ok else 1)
PY
