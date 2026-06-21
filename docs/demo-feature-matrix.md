# Demo Feature Coverage Matrix

Maps each demo to the WineBot features, capabilities, and API endpoints it exercises.

## Feature Sets by Demo

| Feature | Core Pipeline | 7-Zip | Notepad++ | VLC | SuperTux | Hook Demo |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Input / Mouse** | | | | | | |
| `/input/mouse/click` (xdotool) | ✅ | — | — | — | ✅ | — |
| Click with window targeting | ✅ | — | — | — | ✅ | — |
| **Input / Keyboard** | | | | | | |
| `/input/key` text (AHK Send) | ✅ | — | ✅ | — | — | — |
| `/input/key` Return key | ✅ | — | ✅ | — | — | — |
| `/input/key` Tab key | ✅ | — | — | — | — | — |
| `/input/key` Escape key | — | — | — | ✅ | ✅ | — |
| `/input/key` arrow keys (Up/Down) | ✅ | — | — | ✅ | ✅ | — |
| `/input/key` modifier chords (Ctrl+A/S/O, Alt+M/H/F4) | ✅ | — | ✅ | ✅ | ✅ | — |
| **App Launch** | | | | | | |
| `/apps/run` with detach | ✅ | — | ✅ | — | ✅ | — |
| `/apps/run` with args | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| cmd.exe /c (batch scripts) | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| **File Operations** | | | | | | |
| cmd.exe echo/redirect (no dialog) | ✅ | ✅ | — | — | — | — |
| cmd.exe type (read file) | ✅ | — | — | — | — | — |
| docker cp (file deployment) | ✅ | — | — | — | — | — |
| docker exec cat (read from Linux) | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| Archive create/extract | — | ✅ | — | — | — | — |
| **Registry Operations** | | | | | | |
| cmd.exe reg add | ✅ | — | — | — | — | — |
| cmd.exe reg query | ✅ | — | — | — | — | — |
| cmd.exe reg delete | ✅ | — | — | — | — | — |
| **AHK Pipe Dialog** | | | | | | |
| open_gui command | ✅ | — | ✅ | — | — | ✅ |
| set_filename command | ✅ | — | ✅ | — | — | ✅ |
| click_save command | ✅ | — | ✅ | — | — | ✅ |
| click_cancel command | — | — | — | — | — | ✅ |
| File written to disk | ✅ | — | ✅ | — | — | ✅ |
| **Dialog Automation** | | | | | | |
| Dialog watcher (confirmation popups) | ✅ | — | — | — | — | — |
| MessageBox hook (install prompts) | — | — | ✅ | — | — | ✅ |
| Shell32 Browse hook (Open File) | — | — | — | ✅ | — | ✅ |
| **Software Lifecycle** | | | | | | |
| Download installer | — | ✅ | ✅ | ✅ | ✅ | — |
| exe installer /S | — | ✅ | ✅ | ✅ | — | — |
| MSI installer /quiet /qn | — | — | — | — | ✅ | — |
| Launch GUI app | ✅ | — | ✅ | ✅ | ✅ | — |
| Uninstall | — | ✅ | ✅ | ✅ | ✅ | — |
| **Observability** | | | | | | |
| `/screenshot` API | — | — | — | — | ✅ | — |
| Recording + annotations | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Chapter markers | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| CV watcher (pixel diff) | ✅ | — | — | — | — | — |
| **Hook DLLs** | | | | | | |
| winebot_hook (IAT) | ✅ | — | ✅ | ✅ | — | ✅ |
| comdlg32 replacement DLL | — | — | — | — | — | ✅ |
| user32 replacement DLL | — | — | — | — | — | ✅ |
| shell32 replacement DLL | — | — | — | — | — | ✅ |

## Capability Coverage

| Capability Set | Core | 7-Zip | N++ | VLC | SuperTux | Hook |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Control / Agent** | | | | | | |
| Agent launch apps | ✅ | — | ✅ | — | ✅ | — |
| Agent keyboard input | ✅ | — | ✅ | ✅ | ✅ | — |
| Agent mouse input | ✅ | — | — | — | ✅ | — |
| Pipe protocol commands | ✅ | — | ✅ | — | — | ✅ |
| **File I/O** | | | | | | |
| Create files | ✅ | ✅ | ✅ | — | — | — |
| Read files | ✅ | — | ✅ | — | — | — |
| Delete files | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| Archive operations | — | ✅ | — | — | — | — |
| **System Ops** | | | | | | |
| Registry read/write/delete | ✅ | — | — | — | — | — |
| Execute batch scripts | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| **Software Lifecycle** | | | | | | |
| Install programs | — | ✅ | ✅ | ✅ | ✅ | — |
| Uninstall programs | — | ✅ | ✅ | ✅ | ✅ | — |
| Run GUI applications | ✅ | — | ✅ | ✅ | ✅ | — |
| **GUI Interaction** | | | | | | |
| Type text into app | ✅ | — | ✅ | — | — | — |
| Click UI elements | ✅ | — | — | — | ✅ | — |
| Navigate menus | — | — | — | ✅ | ✅ | — |
| Dismiss dialogs | ✅ | — | — | — | — | ✅ |
| Save via dialog replacement | ✅ | — | ✅ | — | — | ✅ |
| **Test Artifacts** | | | | | | |
| Verify file exists | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| Verify file content | ✅ | ✅ | ✅ | — | — | — |
| Visual verification (screenshot) | — | — | — | — | ✅ | — |

## Test Coverage Gap Analysis

| Capability | Demo Coverage | Unit Tests | E2E Tests | Gap |
|:---|:---:|:---:|:---:|:---|
| `/input/mouse/click` bounds validation | ✅ Core | ✅ test_input_validation.py | ✅ test_comprehensive_input.py | None |
| `/input/mouse/click` window targeting | ✅ Core | — | ✅ test_comprehensive_input.py | Minor |
| `/input/key` text injection | ✅ Core + N++ | ✅ test_input_keyboard_conformance.py | ✅ test_input_keyboard.py | None |
| `/input/key` named keys | ✅ Core | ✅ test_input_validation.py | ✅ test_input_keyboard.py | None |
| `/input/key` modifier chords | ✅ Core + N++ | ✅ test_input_validation.py | ✅ test_input_keyboard.py | None |
| `/apps/run` with args | ✅ All demos | ✅ test_api.py | — | E2E gap |
| `/apps/run` with detach | ✅ Core | ✅ test_api.py | — | E2E gap |
| AHK pipe dialog (open_gui/set/click) | ✅ Core + N++ | — | — | Needs test |
| Pipeline demo v5 end-to-end | ✅ Core | — | — | Needs integration test |
| MessageBox hook (IAT) | ✅ Hook demo | — | — | Needs e2e test |
| Shell32 Browse hook | — | — | — | Needs e2e test |
| Install /S flow | ✅ 7-Zip + N++ + VLC | — | — | Needs integration test |
| MSI /quiet flow | ✅ SuperTux | — | — | Needs integration test |
| Download inside container | ✅ All install demos | — | — | Needs network test |
| cv-watcher pixel diff | ✅ Core | — | — | Manual tool |
| cv-analyze issue detection | ✅ Core | — | — | Manual tool |

## Recommendations

1. **Add AHK pipe dialog unit test** — mock the pipe file, verify AHK Gui opens/saves
2. **Add integration test for core pipeline** — run input-pipeline-demo.sh in CI, verify FILE EXISTS
3. **Add e2e test for MessageBox hook** — launch app with winebot_hook=n, verify no prompt appears
4. **Add CV analysis to CI** — cv-analyze should return exit code 1 if HIGH warnings found
5. **Track gaps as GitHub issues** — Shell32 e2e, install/uninstall integration, download network test
