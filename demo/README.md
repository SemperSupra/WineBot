# WineBot Input Pipeline Demo

This directory contains a comprehensive demonstration of the WineBot input pipeline,
showing every input type and capability working end-to-end.

## Quick Start

```bash
# 1. Start WineBot in interactive mode (recording enabled by default)
docker compose -f compose/docker-compose.yml --profile interactive up -d

# 2. Wait for healthy
docker compose -f compose/docker-compose.yml --profile interactive exec winebot-interactive \
  bash -c 'for i in $(seq 1 60); do curl -sf http://localhost:8000/health > /dev/null && break; sleep 2; done'

# 3. Run the demo
bash demo/scripts/input-pipeline-demo.sh

# 4. Copy the recording
docker cp compose-winebot-interactive-1:/artifacts/sessions/SESSION_ID/video_001.mkv demo/output/

# 5. Convert to GIF (optional)
docker exec compose-winebot-interactive-1 sh -c \
  'ffmpeg -i /artifacts/sessions/SESSION_ID/video_001.mkv \
   -vf "fps=10,scale=640:-1:flags=lanczos" -loop 0 /tmp/demo.gif'
docker cp compose-winebot-interactive-1:/tmp/demo.gif demo/output/
```

## What the Demo Shows

The demo exercises the full input pipeline across 5 parts in ~5 minutes:

| Part | Operations | Input Types |
|:---|:---|:---|
| **1. File Create** | Launch Notepad, type content, Ctrl+S save, Alt+F4 close | Agent launch, Mouse click, Keyboard text, Return key, Modifier chords (Ctrl+S, Alt+F4) |
| **2. File Edit** | Re-open Notepad, Ctrl+O open file, edit content, save, close | Agent launch, Modifier chord (Ctrl+O), Keyboard text, Mouse click |
| **3. Registry Create** | Launch Regedit, Tab+Arrow navigate to HKCU\Software, Alt+E menu, create key + string value + DWORD value, verify with reg.exe | Agent launch, Tab key (×4), Arrow keys (×12), Modifier chords (Alt+E, Alt+F4), Keyboard text |
| **4. CMD Script** | Write .bat programmatically via /run/python, execute via /apps/run, verify output — **script reads registry value from Part 3** | Python script execution, App launch with args |
| **5. Cleanup** | Delete all files and registry keys via cmd.exe | App launch with args |

### Input Types Demonstrated

- **Mouse:** Click targeting via xdotool (`/input/mouse/click`)
- **Keyboard plain text:** Typed strings via AHK Send (`/input/key`)
- **Named keys:** Return, Tab, Escape, Down, Right
- **Modifier chords:** Ctrl+S, Ctrl+O, Alt+E, Alt+F4
- **Agent app launch:** `/apps/run` with detach and args
- **Agent script execution:** `/run/python` for programmatic file creation

### Capabilities Demonstrated

- File create, edit, and delete
- Registry key creation with REG_SZ and REG_DWORD values
- Registry verification via reg.exe
- Programmatic batch script: write, execute, verify
- Batch script reads registry values created in prior steps
- Clean artifact removal

## Customizing the Demo

Edit the CONFIG section at the top of `scripts/input-pipeline-demo.sh`:

```bash
API_URL="http://localhost:8000"       # WineBot API URL
DEMO_TEXT_FILE="C:\\artifacts\\..."   # File to create/edit
DEMO_REG_KEY="HKCU\\Software\\..."    # Registry key to create
DEMO_REG_STRING_VALUE="..."           # String value content
DEMO_REG_DWORD_VALUE="42"             # DWORD value
```

## Files

```
demo/
├── README.md                         # This file
├── scripts/
│   └── input-pipeline-demo.sh        # Main demo script (editable)
└── output/                           # Recording output (gitignored)
    ├── demo.mkv                      # Video recording with subtitles
    └── demo.gif                      # Animated GIF preview
```

## Requirements

- Docker Desktop running
- WineBot container started in interactive mode
- `curl`, `docker` CLI tools available
