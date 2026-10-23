#!/usr/bin/env bash
# Public disposable WineBot/Linux/Wine GUI probe; no sovereign host data.
set -euo pipefail
test "$GITHUB_ACTIONS" = true || exit 2
cd "$(dirname "$0")/../.."
export BUILD_INTENT=rel WINEBOT_IMAGE_VERSION=uxref
export WINEBOT_INPUT_TRACE=0 WINEBOT_INPUT_TRACE_WINDOWS=0 WINEBOT_RECORD=0
export WINEBOT_TELEMETRY=0 WINEBOT_PERF_METRICS=0 WINEBOT_SUPERVISE_EXPLORER=0
export WINEBOT_ALLOW_HEADLESS_HYBRID=0 DOCKER_BUILD_RECORD_UPLOAD=false
export API_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
echo "::add-mask::$API_TOKEN"
mkdir -p artifacts/public-wine-gui
finish() {
  docker compose -f compose/docker-compose.yml --profile headless down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap finish EXIT
echo "WINEBOT_IMAGE_BUILD=START"
if ! docker build --target intent-rel -f docker/Dockerfile -t winebot:uxref-rel . >/tmp/public-wine-build.log 2>&1; then
  echo "WINEBOT_IMAGE_BUILD=FAILED"
  exit 1
fi
echo "WINEBOT_IMAGE_BUILD=PASS"
docker compose -f compose/docker-compose.yml --profile headless up -d --no-build winebot >/dev/null
CID="$(docker compose -f compose/docker-compose.yml ps -q winebot)"
test -n "$CID" || { echo "WINEBOT_CONTAINER=ABSENT"; exit 1; }
status=not-ready
for i in $(seq 1 100); do
  status="$(docker inspect -f '{{.State.Health.Status}}' "$CID" 2>/dev/null || echo absent)"
  test "$status" = healthy && break
  sleep 3
done
echo "WINEBOT_API_HEALTH=$status"
test "$status" = healthy || exit 1
docker exec -u winebot -e DISPLAY=:99 "$CID" sh -lc \
  'command -v wine >/dev/null && command -v xdotool >/dev/null && command -v import >/dev/null'
echo "WINEBOT_WINE_X11_CAPTURE_PREREQS=PASS"
# WineBot owns its bind-mounted artifact tree as UID 1000; restore this runner's
# write access for only the public output directory after guest startup.
sudo chown -R "$(id -u):$(id -g)" artifacts/public-wine-gui
docker exec -u winebot "$CID" sh -lc \
 'mkdir -p /tmp/public-wine-gui; printf "%s\n" "WineBot synthetic Notepad text" "Human: readable app UI" "Assistive: keyboard+focus" "Automation: reproducible test" "Agents: observe-act-verify" > /tmp/public-wine-gui/demo.txt'
printf 'app,launched,window_visible,window_capture\n' > artifacts/public-wine-gui/results.csv
for spec in 'notepad|notepad.exe|[Nn]otepad' \
            'winefile|winefile.exe|[Ww]ine [Ff]ile|[Ff]ile [Mm]anager|winefile' \
            'winecfg|winecfg.exe|[Ww]ine configuration|[Ww]ine [Cc]onfiguration' \
            'regedit|regedit.exe|[Rr]egistry [Ee]ditor|[Rr]egedit'; do
  IFS='|' read -r app exe title_regex <<< "$spec"
  launch=0 visible=0 capture=0
  if test "$app" = notepad; then
    docker exec -d -u winebot -e DISPLAY=:99 -e WINEDEBUG=-all "$CID" \
      bash -lc 'wine notepad.exe "$(winepath -w /tmp/public-wine-gui/demo.txt)" >/tmp/public-wine-gui/notepad.log 2>&1' && launch=1
  else
    docker exec -d -u winebot -e DISPLAY=:99 -e WINEDEBUG=-all "$CID" \
      bash -lc "wine $exe >/tmp/public-wine-gui/$app.log 2>&1" && launch=1
  fi
  window=''
  for i in $(seq 1 24); do
    found="$(docker exec -u winebot -e DISPLAY=:99 "$CID" xdotool search --onlyvisible --name "$title_regex" 2>/dev/null || true)"
    window="$(printf '%s\n' "$found" | grep -E '^[0-9]+$' | tail -n 1 || true)"
    test -n "$window" && break
    sleep 1
  done
  if test -n "$window"; then
    visible=1
    # Local, read-only semantic API probe with allowlisted booleans/count classes.
    # Never print WinInspect process/window details, HWNDs, paths, or API tokens.
    if test "$app" = notepad; then
      if ! docker exec -i -u winebot -e API_TOKEN="$API_TOKEN" "$CID" python3 - <<'PY' > artifacts/public-wine-gui/semantic.tmp 2>/dev/null
import json, os, urllib.error, urllib.request
root="http://127.0.0.1:8000"
token=os.environ["API_TOKEN"]
def check(path):
    req=urllib.request.Request(root+path, headers={"X-API-Key": token})
    try:
        with urllib.request.urlopen(req, timeout=9) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as err:
        return err.code, None
    except Exception:
        return 0, None
xc,xd=check("/windows")
cc,cd=check("/wininspect/capabilities")
wc,wd=check("/wininspect/windows")
count=wd.get("count") if isinstance(wd,dict) else None
cls=("unavailable" if type(count) is not int else
    "zero" if count==0 else "one" if count==1 else "two-plus")
print(json.dumps({"x11_windows_api_ok": xc==200,
 "wininspect_capabilities_ok": cc==200,
 "wininspect_windows_ok": wc==200,
 "wininspect_window_count_class": cls}))
PY
      then
        echo '{"x11_windows_api_ok":false,"wininspect_capabilities_ok":false,"wininspect_windows_ok":false,"wininspect_window_count_class":"unavailable"}' > artifacts/public-wine-gui/semantic.tmp
      fi
    fi
    if docker exec -u winebot -e DISPLAY=:99 "$CID" bash -lc \
      'import -display :99 -window "$1" "png:/tmp/public-wine-gui/$2.png" >/dev/null 2>&1 && convert "/tmp/public-wine-gui/$2.png" -strip "/tmp/public-wine-gui/$2.png"' _ "$window" "$app"; then
      if docker cp "$CID:/tmp/public-wine-gui/$app.png" "artifacts/public-wine-gui/$app.png" >/dev/null 2>&1; then capture=1; fi
    fi
    docker exec -u winebot -e DISPLAY=:99 "$CID" xdotool windowclose "$window" >/dev/null 2>&1 || true
  fi
  printf '%s,%s,%s,%s\n' "$app" "$launch" "$visible" "$capture" >> artifacts/public-wine-gui/results.csv
  echo "WINEBOT_APP_$(echo "$app" | tr '[:lower:]' '[:upper:]')=LAUNCH:$launch,WINDOW:$visible,CAPTURE:$capture"
done
python3 - <<'PY'
import csv,json,os,pathlib,struct
root=pathlib.Path("artifacts/public-wine-gui")
items=list(csv.DictReader((root/"results.csv").open()))
assert len(items)==4
photos=[]
for item in items:
    f=root/(item["app"]+".png")
    if f.exists():
        b=f.read_bytes()[:24]
        if b[:8]!=b"\x89PNG\r\n\x1a\n": raise ValueError("invalid PNG")
        w,h=struct.unpack(">II",b[16:24])
        if not 170<=w<=1800 or not 90<=h<=1300:
            f.unlink()
            item["window_capture"]="0"
            continue
        photos.append({"app":item["app"],"width":w,"height":h})
(root/"results.csv").unlink()
semantic_path=root/"semantic.tmp"
semantic=json.loads(semantic_path.read_text()) if semantic_path.is_file() else {}
semantic_path.unlink(missing_ok=True)
dpi=int(os.environ.get("WINE_DPI","96"))
smoothing=os.environ.get("WINE_FONT_SMOOTHING","grayscale")
if dpi not in (96,120,144,192) or smoothing not in ("off","grayscale","cleartype"):
    raise ValueError("Unexpected Wine UI profile")
(root/"public_results.json").write_text(json.dumps({
 "wine_dpi":dpi,
 "font_smoothing":smoothing,
 "semantic_probe":semantic,
 "schema":"winebot.synthetic-window-rdte.v1",
 "venue":"WineBot intent-rel container on disposable public Ubuntu CI",
 "results":items,
 "image_dimensions":photos,
 "limits":"X11 window captures, not broker-mediated input or assistive-technology acceptance"
},indent=2)+"\n")
print("WINEBOT_WINDOW_SCREENSHOTS="+str(len(photos)))
print("PUBLIC_MANIFEST=ALLOWLIST_ONLY")
PY
