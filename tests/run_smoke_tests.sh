#!/usr/bin/env bash
set -e

echo "--- Starting Windows Automation Smoke Tests ---"

# 0. Environment Verification
echo "Verifying environment..."
if [ -z "$DISPLAY" ]; then
    echo "Error: DISPLAY not set."
    exit 1
fi

if ! xdpyinfo >/dev/null 2>&1; then
    echo "Error: Xvfb not reachable on $DISPLAY"
    exit 1
fi

echo "Checking Wine driver..."
if ! wine cmd /c "echo Driver OK" >/dev/null 2>&1; then
    echo "Error: Wine driver failed to initialize (check logs for nodrv)"
    wine cmd /c "echo test" 2>&1 | head -n 20
    exit 1
fi
echo "Environment OK."

# Helper to take screenshot
take_screenshot() {
    local name="$1"
    echo "Taking screenshot: $name"
    import -window root "/tmp/screenshot_${name}.png" || echo "Warning: screenshot failed"
}

# 1. AutoIt
echo "Testing AutoIt..."
autoit tests/test_autoit.au3
take_screenshot "autoit"
echo "AutoIt test complete."

# 2. AutoHotkey
echo "Testing AutoHotkey..."
ahk tests/test_ahk.ahk
take_screenshot "ahk"
echo "AutoHotkey test complete."

# 3. X11 Helpers
echo "Testing X11 helpers..."
/automation/bin/x11.sh list-windows
active_id=$(/automation/bin/x11.sh active-window)
echo "Active window ID: $active_id"
# Only try getting title if we have a valid ID
if [[ "$active_id" != "No active window" ]]; then
    /automation/bin/x11.sh window-title "$active_id" || echo "Warning: Could not get title (window likely closed)"
fi
/automation/bin/x11.sh search --name ".*"
take_screenshot "x11_helper"
echo "X11 helpers test complete."

# 4. AHK execution via winebotctl
echo "Testing AHK execution via winebotctl..."
# Use existing test script and focus syntax (even if target missing)
/scripts/bin/winebotctl run ahk --file tests/test_ahk.ahk --focus-title "Shell_TrayWnd" > /tmp/run_ahk_test.log
if [ -f /tmp/run_ahk_test.log ]; then
    echo "winebotctl ahk output captured."
    cat /tmp/run_ahk_test.log
else
    echo "Error: winebotctl ahk output missing."
    exit 1
fi
echo "winebotctl ahk test complete."

# 5. Inspectors (Installation & Launch)
echo "Testing Inspectors..."
/scripts/setup/install-inspectors.sh

# Helper to test background launch
test_launch() {
    local command="$1"
    local name="$2"
    echo "Launching $name..."
    bash -lc "$command" &
    local pid=$!
    sleep 5
    if kill -0 "$pid" 2>/dev/null; then
        echo "$name running (PID $pid). Killing..."
        kill "$pid"
    else
        echo "Error: $name failed to start or exited early."
        exit 1
    fi
}

test_launch "/scripts/internal/au3info.sh" "Au3Info"
if [ -f /scripts/diagnostics/smoke-wininspect.sh ]; then
    bash /scripts/diagnostics/smoke-wininspect.sh /tmp/wininspect_smoke
else
    echo "Error: WinInspect smoke script not found."
    exit 1
fi

echo "Inspector tests complete."

# 6. Windows Python (winpy)
echo "Testing winpy..."
if command -v winpy >/dev/null 2>&1; then
    winpy -c "import sys; print(f'Hello from winpy {sys.version}')" > /tmp/winpy_test.log
    if grep -q "Hello from winpy" /tmp/winpy_test.log; then
        echo "winpy operational."
        cat /tmp/winpy_test.log
    else
        echo "Error: winpy failed to produce expected output."
        exit 1
    fi
else
    echo "Warning: winpy not found in PATH."
fi
echo "winpy test complete."

# 7. Screenshot Directory Argument
echo "Testing screenshot directory arg..."
mkdir -p /tmp/screenshots_test_dir
/automation/bin/screenshot.sh /tmp/screenshots_test_dir
if ls /tmp/screenshots_test_dir/screenshot_*.png >/dev/null 2>&1; then
    echo "Screenshot saved to directory."
else
    echo "Error: Screenshot not saved to target directory."
    exit 1
fi
echo "Screenshot directory test complete."

# 8. Advanced Screenshot Features
echo "Testing screenshot flags (--label, --delay)..."
adv_shot="/tmp/screenshot_advanced.png"
/automation/bin/screenshot.sh --window root --delay 1 --label "SmokeTest" "$adv_shot"
if [ -f "$adv_shot" ]; then
    echo "Advanced screenshot created."
else
    echo "Error: Advanced screenshot failed."
    exit 1
fi
echo "Advanced screenshot test complete."

# Required single smoke evidence file
/automation/bin/screenshot.sh --window root --delay 1 --label "WindowsAutomationSmoke" /tmp/smoke_test.png
if [ ! -s /tmp/smoke_test.png ]; then
    echo "Error: /tmp/smoke_test.png missing or empty."
    exit 1
fi

echo "--- All tests passed! ---"
