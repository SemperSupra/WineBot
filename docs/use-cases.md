# WineBot Use Cases & Software Loadouts

Each use case defines a software loadout — the specific Linux and Windows tools
needed to accomplish the automation task. Loadouts are specified via
`WINE_WINETRICKS` at container boot.

## Loadout Configuration

Loadouts are specified as comma-separated `WINE_WINETRICKS` values at startup:

```bash
docker compose -f compose/docker-compose.yml --profile headless up -d
# Loadout is baked into the image via .../install-loadout.sh or set at runtime:
WINE_WINETRICKS=vcrun2019,dotnet48 docker compose up -d
```

## Use Case 1: Automated Installer QA

**What:** QA teams testing Windows installers in CI/CD pipelines.
**Approach:** Download installer, silent install, verify files/registry/function, screenshot, uninstall, score.

| Tool | Source | Purpose |
|:---|:---|:---|
| curl | Linux (host) | Download installers |
| file | Linux | Identify binary type |
| sha256sum | Linux | Integrity verification |
| cmd.exe | Wine (built-in) | Run installers, create/verify files |
| reg.exe | Wine (built-in) | Verify registry entries |
| certutil.exe | Wine (built-in) | SHA256 hash from Windows side |
| /screenshot API | WineBot | Visual verification |

**No additional winetricks needed.** All tools are built-in.

## Use Case 2: Legacy App Automation

**What:** Wrap old Windows applications in a REST API for agent-driven automation.
**Approach:** Install legacy app, launch it, interact via `/input/key` and `/input/mouse/click`, handle dialogs with hook DLLs.

| Tool | Source | Purpose |
|:---|:---|:---|
| AHK | Wine (pre-installed) | Keyboard/mouse injection, pipe dialog |
| AutoIt | Wine (pre-installed) | Alternative automation backend |
| winebot_hook.dll | Wine (pre-installed) | Dialog interception (ComDlg32, User32, Shell32) |
| dialog_watcher.ahk | Wine (pre-installed) | Confirmation popup dismissal |
| /input/key API | WineBot | Typed text input |
| /input/mouse/click API | WineBot | Mouse targeting |

**Required winetricks:** `vcrun2019` (many legacy apps need Visual C++ runtime)

## Use Case 3: Headless CI/CD Build Pipeline

**What:** Build Windows software artifacts in a headless container.
**Approach:** Create source files, compile/build, checksum, package, deploy.

| Tool | Source | Purpose |
|:---|:---|:---|
| cmd.exe | Wine (built-in) | Build scripts |
| cabarc.exe | Wine (built-in) | CAB/archive packaging |
| certutil.exe | Wine (built-in) | SHA256 checksums |
| dotnet CLI | Wine (winetricks dotnet48) | .NET build toolchain |
| MSBuild | Wine (winetricks dotnet48) | .NET project compilation |
| Python 3.13 | Wine (pre-installed) | Scripted build steps |
| /apps/run API | WineBot | Execute build commands |

**Required winetricks:** `dotnet48` (for .NET builds)

## Use Case 4: Reverse Engineering Sandbox

**What:** Analyze Windows binaries in a controlled, observable runtime.
**Approach:** Linux tools for surface analysis, Wine runtime for behavior observation, /proc for memory inspection.

| Tool | Source | Purpose |
|:---|:---|:---|
| file | Linux (host) | Binary identification |
| strings | Linux (host) | Extract readable text |
| sha256sum | Linux (host) | File integrity |
| objdump/readelf | Linux (host) | PE structure analysis |
| /proc/PID/maps | Linux (kernel) | Memory layout inspection |
| /proc/PID/mem | Linux (kernel) | Raw memory reading |
| strace | Linux (host) | System call tracing |
| certutil.exe | Wine (built-in) | Windows-side hash |
| reg.exe | Wine (built-in) | Registry inspection |
| wine_dbg | Wine (built-in) | Wine debug channels |
| /screenshot API | WineBot | Visual observation |
| /input/key API | WineBot | Interactive control |

**No additional winetricks needed.** Linux analysis tools are host-side.

## Use Case 5: Installer Builder / Repackager

**What:** Automatically build Windows installers, test them, and package for deployment.
**Approach:** Build installer via NSIS/WiX, test in headless Wine, package for distribution.

| Tool | Source | Purpose |
|:---|:---|:---|
| NSIS (makensis) | Wine (winetricks nsis) | Build NSIS installers |
| WiX Toolset | Wine (winetricks dotnet48) | Build MSI installers |
| cmd.exe | Wine (built-in) | Build orchestration |
| 7-Zip | Wine (manual install) | Extract/repack archives |
| certutil.exe | Wine (built-in) | Signing verification |
| /apps/run API | WineBot | Execute build toolchain |
| Installer QA demo | WineBot | Test the built installer |

**Required winetricks:** `nsis, dotnet48`

## Use Case 6: Batch File Processing (Graphics/OCR/PDF)

**What:** Process files through Windows-only tools in a headless pipeline.
**Approach:** Feed files into Wine, process via Windows tools, extract output.

| Tool | Source | Purpose |
|:---|:---|:---|
| IrfanView | Wine (manual install, /silent) | Batch image conversion |
| ImageMagick | Linux (apt) | Cross-platform image processing |
| Ghostscript | Linux (apt) | PDF manipulation |
| 7-Zip | Wine (manual install) | Archive extraction/packaging |
| cmd.exe | Wine (built-in) | Orchestration |
| /apps/run API | WineBot | Execute processing commands |

**Required winetricks:** none for core image processing (IrfanView /silent install)

## Loadout Summary Table

| Use Case | WINE_WINETRICKS | Linux Tools | Windows Tools | Demo Script |
|:---|:---|:---|:---|:---|
| Installer QA | (none) | curl, file, sha256sum | cmd.exe, reg, certutil | `demo-installer-qa.sh` |
| Legacy App Automation | `vcrun2019` | (none) | AHK, AutoIt, hook DLLs | `demo-notepadpp.sh` |
| CI/CD Build | `dotnet48` | (none) | cmd.exe, cabarc, certutil | `demo-ci-pipeline.sh` |
| Reverse Engineering | (none) | file, strings, sha256sum, strace | certutil, reg, wine_dbg | `demo-winebox.sh` |
| Installer Builder | `nsis,dotnet48` | (none) | NSIS, WiX, cmd.exe | (build + demo-installer-qa.sh) |
| Batch File Processing | (none) | ImageMagick, Ghostscript | IrfanView, 7-Zip | (custom pipeline) |

## How to Add a New Loadout

1. **Define the tools** — what Linux, Wine built-in, and installable tools are needed
2. **Add winetricks** — if a Windows DLL/runtime is required, add to `WINE_WINETRICKS`
3. **Create demo script** — in `demo/scripts/` following the existing patterns
4. **Add to demo-readme** — document the use case in `demo/README.md`
5. **Add to this doc** — add a row to the loadout table
