#!/usr/bin/env bash
set -e

echo "--- Starting Windows Automation Smoke Tests ---"

# Ensure we have a display
if [ -z "$DISPLAY" ]; then
    echo "Error: DISPLAY not set. Are you running inside the container?"
    exit 1
fi

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
/automation/x11.sh list-windows
active_id=$(/automation/x11.sh active-window)
echo "Active window ID: $active_id"
# Only try getting title if we have a valid ID
if [[ "$active_id" != "No active window" ]]; then
    /automation/x11.sh window-title "$active_id"
fi
/automation/x11.sh search --name ".*"
take_screenshot "x11_helper"
echo "X11 helpers test complete."

# 4. run-ahk helper
echo "Testing run-ahk helper..."
# Use existing test script, test focus syntax (even if target missing) and logging
/scripts/run-ahk.sh tests/test_ahk.ahk --focus-title "Shell_TrayWnd" --log /tmp/run_ahk_test.log
if [ -f /tmp/run_ahk_test.log ]; then
    echo "run-ahk log created."
    cat /tmp/run_ahk_test.log
else
    echo "Error: run-ahk log missing."
    exit 1
fi
echo "run-ahk helper test complete."

# 5. Inspectors (Installation & Launch)
echo "Testing Inspectors..."
/scripts/install-inspectors.sh

# Helper to test background launch
test_launch() {
    local script="$1"
    local name="$2"
    echo "Launching $name..."
    "$script" &
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

test_launch "/scripts/au3info.sh" "Au3Info"
test_launch "/scripts/winspy.sh" "WinSpy"

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
/automation/screenshot.sh /tmp/screenshots_test_dir
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
/automation/screenshot.sh --window root --delay 1 --label "SmokeTest" "$adv_shot"
if [ -f "$adv_shot" ]; then
    echo "Advanced screenshot created."
else
    echo "Error: Advanced screenshot failed."
    exit 1
fi
echo "Advanced screenshot test complete."

echo "--- All tests passed! ---"