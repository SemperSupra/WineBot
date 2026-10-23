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
import csv,json,pathlib,struct
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
(root/"public_results.json").write_text(json.dumps({
 "schema":"winebot.synthetic-window-rdte.v1",
 "venue":"WineBot intent-rel container on disposable public Ubuntu CI",
 "results":items,
 "image_dimensions":photos,
 "limits":"X11 window captures, not broker-mediated input or assistive-technology acceptance"
},indent=2)+"\n")
print("WINEBOT_WINDOW_SCREENSHOTS="+str(len(photos)))
print("PUBLIC_MANIFEST=ALLOWLIST_ONLY")
PY
