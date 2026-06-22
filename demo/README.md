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

# 3. Run any demo (all source _demo_common.sh for shared functions)
bash demo/scripts/input-pipeline-demo.sh        # Core input pipeline
bash demo/scripts/demo-7zip.sh                  # 7-Zip install → archive → verify
bash demo/scripts/demo-notepadpp.sh             # Notepad++ install → edit → save
bash demo/scripts/demo-vlc.sh                   # VLC install → menu navigation
bash demo/scripts/demo-supertux.sh              # SuperTux game install → play → close
bash demo/scripts/demo-ci-pipeline.sh           # Headless CI/CD build pipeline
bash demo/scripts/demo-winebox.sh               # RE sandbox — dual toolchain analysis
bash demo/scripts/demo-installer-qa.sh          # Installer QA — PASS/FAIL pipeline
bash demo/scripts/hook-demo.sh                  # API hook DLL tests (all dialog types)

# 4. Copy output (auto-trimmed to remove blank intro)
docker cp compose-winebot-interactive-1:/tmp/trimmed.mkv demo/output/<name>.mkv
docker cp compose-winebot-interactive-1:/tmp/trimmed.gif demo/output/<name>.gif
docker cp compose-winebot-interactive-1:/artifacts/sessions/SESSION_ID/events_001.vtt demo/output/<name>.vtt
```

## Architecture

All demos source `_demo_common.sh` which provides shared functions:
- **Session**: `init_session` — token detection, session ID, lease acquisition
- **Recording**: `ann()` (annotation), `ch()` (chapter marker), `stop_recording` (stop + smart trim)
- **Download/Install**: `linux_dl()`, `wine_install()`, `wine_msi_install()`, `wine_msi_uninstall()`, `wine_cmd()`
- **Input**: `type_text()`, `press_key()`, `click_notepad()`, pipe protocol (`pipe_cmd`, `pipe_read`, `pipe_wait`)
- **File Ops**: `verify_file()` / `vf()`, `check()`, `write_file()`, `bat()` (.bat execution)
- **AHK**: `setup_ahk_handler([watcher_flag])` — deploys and launches dialog replacement
- **QA**: `pass()`, `fail()` with `$PASS`/`$FAIL` counters

Smart trimming is provided by `_trim.sh` (chapter-based, auto-strips blank intro).

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

### 6. CI/CD Pipeline Demo (`demo-ci-pipeline.sh`)
Headless Windows build pipeline using only Wine built-in tools.

| Phase | Operation | Method |
|:---|:---|:---|
| Build sources | Create 3 source files + manifest | `write_file()` (Linux direct) |
| Checksums | SHA256 via certutil | `bat()` → cmd.exe /c |
| Package | CAB archive via cabarc | `bat()` → cmd.exe /c |
| Registry | Build metadata via reg add | `bat()` → cmd.exe /c |
| GUI Report | Notepad + /input/key + pipe save | `/input/key` + AHK pipe |
| Validation | Verify all artifacts | `docker exec` (Linux-side) |
| Cleanup | Remove files + registry | `bat()` + `docker exec` |

### 7. RE Sandbox Demo (`demo-winebox.sh`)
Reverse engineering Windows binaries with dual Linux/Windows toolchain.

| Phase | Operation | Tools |
|:---|:---|:---|
| Acquire | Download sample binary | Linux curl |
| Surface analysis | File type, strings, hash | `file`, `strings`, `sha256sum` |
| Windows analysis | Windows hash, launch binary | `certutil`, `/apps/run` |
| Runtime | Screenshot, process enum | `/screenshot`, `ps aux` |
| Memory | Inspect process maps | `/proc/PID/maps` |
| Registry | Check for artifacts | `reg query` via `bat()` |
| Cleanup | Remove sample, forensic capture | `docker exec` |

### 8. Installer QA Demo (`demo-installer-qa.sh`)
Automated QA pipeline with PASS/FAIL counters.

| Step | Operation | Verification |
|:---|:---|:---|
| Download | curl inside container | File size check |
| Install | Silent `/S` install | 4 expected files verified |
| Registry | reg add + reg query | Registry entries confirmed |
| Functional | Create + extract archive | Archive creation + extraction |
| Screenshot | `/screenshot` API | File size > 1KB |
| Uninstall | Silent uninstall | All 4 files confirmed removed |
| Report | PASS/FAIL summary | Pass/fail counters |

### 9. Hook Demo (`hook-demo.sh`)
API hook DLL validation across all Wine dialog types.

| Test | Dialog Type | Handler |
|:---|:---|:---|
| TEST 1 | user32!MessageBoxW | IAT hook auto-dismiss |
| TEST 2 | comdlg32!GetSaveFileNameW | AHK pipe dialog |
| TEST 3 | shell32!SHBrowseForFolderW | AHK pipe dialog |

## Demo Features

All demos include:
- **Chapter markers** — navigable in VLC/MPV timeline
- **Subtitle annotations** — every step labeled
- **Auto-trim** — blank intro seconds removed via `_trim.sh`
- **GIF generation** — animated preview alongside MKV video
- **Recording** — full desktop captured by WineBot recorder
- **Shared library** — `_demo_common.sh` eliminates code duplication

## Files

```
demo/
├── README.md                           # This file
├── scripts/
│   ├── _demo_common.sh                 # Shared functions sourced by all demos
│   ├── _trim.sh                        # Smart-trim helper (chapter-based)
│   ├── input-pipeline-demo.sh          # Core input pipeline demo
│   ├── hook-demo.sh                    # API hook DLL demonstration
│   ├── demo-7zip.sh                    # 7-Zip install/archive demo
│   ├── demo-notepadpp.sh               # Notepad++ text editor demo
│   ├── demo-vlc.sh                     # VLC media player demo
│   ├── demo-supertux.sh                # SuperTux game demo
│   ├── demo-ci-pipeline.sh             # Headless CI/CD build pipeline
│   ├── demo-winebox.sh                 # Reverse engineering sandbox
│   ├── demo-installer-qa.sh            # Installer QA pipeline
│   └── CmdScript_Demo.bat              # Batch script template
└── output/                             # Generated files (gitignored)
    ├── .gitignore
    ├── core-pipeline.mkv / .gif        # Input pipeline demo output
    ├── ci-pipeline.mkv / .gif          # CI/CD pipeline demo output
    ├── re-sandbox.mkv / .gif           # RE sandbox demo output
    ├── 7zip.mkv / .gif                 # 7-Zip demo output
    ├── notepadpp.mkv / .gif            # Notepad++ demo output
    ├── vlc.mkv / .gif                  # VLC demo output
    ├── supertux.mkv / .gif             # SuperTux demo output
    ├── installer-qa.mkv / .gif         # Installer QA demo output
    ├── demo.gif / .vtt                 # Legacy demo output
    └── ...
```

## Requirements

- Docker Desktop running
- WineBot container started in interactive mode
- Container needs internet access (for download demos)
- `curl`, `docker` CLI tools available on host
