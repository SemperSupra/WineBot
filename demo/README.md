# WineBot Demos

This directory contains focused demo scripts that exercise WineBot capabilities
end-to-end. Each demo downloads software, installs it, interacts via the API,
verifies artifacts, and cleans up — all with recorded video, chapter markers,
and subtitle annotations.

## Quick Start

```bash
# 1. Start WineBot in interactive mode
docker compose -f compose/docker-compose.yml --profile interactive up -d

# 2. Wait for healthy
for i in $(seq 1 60); do
  docker compose -f compose/docker-compose.yml --profile interactive exec winebot-interactive \
    curl -sf http://localhost:8000/health > /dev/null && break
  sleep 5
done

# 3. Run any demo
bash demo/scripts/input-pipeline-demo.sh        # Core input pipeline
bash demo/scripts/demo-7zip.sh                  # 7-Zip install → archive → verify
bash demo/scripts/demo-notepadpp.sh             # Notepad++ install → edit → save
bash demo/scripts/demo-vlc.sh                   # VLC install → menu navigation
bash demo/scripts/demo-supertux.sh              # SuperTux game install → play → close

# 4. Copy output (auto-trimmed to remove blank intro)
docker cp compose-winebot-interactive-1:/tmp/trimmed.mkv demo/output/demo.mkv
docker cp compose-winebot-interactive-1:/tmp/trimmed.gif demo/output/demo.gif
docker cp compose-winebot-interactive-1:/artifacts/sessions/SESSION_ID/events_001.vtt demo/output/demo.vtt
```

## Demo Catalog

### 1. Input Pipeline Demo (`input-pipeline-demo.sh`)
The core demo. Exercises every input type and capability.

| Part | Operations | API Endpoints |
|:---|:---|:---|
| Setup | AHK pipe handler + dialog watcher | `/apps/run` |
| Mouse + Keyboard | Type text, named keys (Return, Tab), modifier chords (Ctrl+A) | `/input/key`, `/input/mouse/click` |
| AHK Dialog | Pipe protocol: `open_gui` → `set_filename` → `click_save` | Pipe file |
| File Ops | cmd.exe /c echo/redirect/type | `/apps/run` |
| Registry | cmd.exe /c reg add/query/delete | `/apps/run` |
| Batch Script | docker cp + cmd.exe /c execution | `/apps/run` |
| Cleanup | All files and registry keys removed | `/apps/run` |

### 2. 7-Zip Archive Demo (`demo-7zip.sh`)
Pure cmd.exe /c operations, no GUI needed.

| Step | What It Tests |
|:---|:---|
| Download | curl inside Wine container |
| Silent install | `installer.exe /S` |
| Archive create | `7z a` via cmd.exe /c |
| Archive extract | `7z x` via cmd.exe /c |
| File verification | Compare original vs extracted |
| Uninstall | `Uninstall.exe /S` cleanup |

### 3. Notepad++ Demo (`demo-notepadpp.sh`)
GUI text editor with MessageBox hook and Save dialog.

| Step | What It Tests |
|:---|:---|
| Download | GitHub release download |
| Silent install | `installer.exe /S` — **MessageBox hook dismisses prompts** |
| Launch | `/apps/run` notepad++.exe |
| Keyboard input | `/input/key` types content into editor |
| Save dialog | **AHK pipe dialog** replaces Wine Save As |
| File verification | Read saved file from disk |
| Uninstall | Silent uninstall + cleanup |

### 4. VLC Media Player Demo (`demo-vlc.sh`)
Complex GUI with menu navigation and Open File dialog.

| Step | What It Tests |
|:---|:---|
| Download | ~20MB installer from videolan.org |
| Silent install | `installer.exe /S` |
| Launch | `cmd.exe /c vlc.exe` with flags |
| Menu navigation | Alt+M (Media), Alt+H (Help), arrow keys |
| Keyboard chords | Alt+key combos on GUI menus |
| Open File dialog | Ctrl+O — **Shell32 hook intercepts** |
| Close + uninstall | Alt+F4 + silent uninstall |

### 5. SuperTux Game Demo (`demo-supertux.sh`)
Full game lifecycle: MSI installer, GPU rendering, complex input.

| Step | What It Tests |
|:---|:---|
| Download | ~200MB MSI from GitHub |
| Install via MSI | **msiexec /quiet /qn** (MSI hook) |
| Launch | `/apps/run` supertux2.exe |
| Keyboard nav | Up/Down/Return on game menus |
| Mouse click | `/input/mouse/click` on game window |
| Screenshot | `/screenshot` captures game rendering |
| Close + uninstall | Escape + Alt+F4 + msiexec /x |
| Full lifecycle | Download → Install → Play → Verify → Remove |

## Demo Features

All demos include:
- **Chapter markers** — navigable in VLC/MPV timeline
- **Subtitle annotations** — every step labeled
- **Auto-trim** — blank intro seconds removed (configurable via `TRIM_SS`)
- **GIF generation** — animated preview alongside MKV video
- **Recording** — full desktop captured by WineBot recorder

## Files

```
demo/
├── README.md                           # This file
├── scripts/
│   ├── input-pipeline-demo.sh          # Core input pipeline demo
│   ├── hook-demo.sh                    # API hook DLL demonstration
│   ├── demo-7zip.sh                    # 7-Zip install/archive demo
│   ├── demo-notepadpp.sh               # Notepad++ text editor demo
│   ├── demo-vlc.sh                     # VLC media player demo
│   ├── demo-supertux.sh                # SuperTux game demo
│   └── CmdScript_Demo.bat              # Batch script template
└── output/                             # Generated files (gitignored)
    ├── .gitignore
    ├── demo.mkv                        # Trimmed video with chapters
    ├── demo.gif                        # Animated GIF preview
    └── demo.vtt                        # Subtitle track
```

## Requirements

- Docker Desktop running
- WineBot container started in interactive mode
- Container needs internet access (for download demos)
- `curl`, `docker` CLI tools available on host
