#!/usr/bin/env bash
set -e

# scripts/install-theme.sh
# Configures Wine visual settings for optimal Automation, CV, and Usability.

echo "--> Applying WineBot Theme & Optimizations..."

# 1. Font Linking (Replacements for missing Windows fonts)
# Maps Segoe UI/Tahoma -> Liberation Sans (Metric compatible)
cat <<EOF > /tmp/fonts.reg
REGEDIT4

[HKEY_CURRENT_USER\Software\Wine\Fonts\Replacements]
"Segoe UI"="Liberation Sans"
"Arial"="Liberation Sans"
"Tahoma"="Liberation Sans"
"Verdana"="Liberation Sans"
"Times New Roman"="Liberation Serif"
"Courier New"="Liberation Mono"
"Consolas"="Liberation Mono"
"Lucida Console"="Liberation Mono"

[HKEY_LOCAL_MACHINE\Software\Microsoft\Windows NT\CurrentVersion\FontSubstitutes]
"Segoe UI"="Liberation Sans"
"Arial"="Liberation Sans"
"Tahoma"="Liberation Sans"
"Verdana"="Liberation Sans"
"Times New Roman"="Liberation Serif"
"Courier New"="Liberation Mono"
"Consolas"="Liberation Mono"
"Lucida Console"="Liberation Mono"
EOF

# 2. CV & Performance Optimizations
# - Disable animations (Fade, Slide) for instant UI state
# - Set solid background colors for contrast
# - Ensure predictable window metrics
cat <<EOF > /tmp/theme.reg
REGEDIT4

[HKEY_CURRENT_USER\Control Panel\Desktop]
"FontSmoothing"="2"
"FontSmoothingType"=dword:00000001
"FontSmoothingGamma"=dword:00000000
"FontSmoothingOrientation"=dword:00000001
"UserPreferencesMask"=hex:90,12,03,80
"MenuShowDelay"="0"
"ForegroundLockTimeout"=dword:00000000
"DragFullWindows"="0"

[HKEY_CURRENT_USER\Control Panel\Colors]
"Background"="58 110 165"
"AppWorkspace"="128 128 128"
"Window"="255 255 255"
"WindowText"="0 0 0"
"Menu"="212 208 200"
"MenuText"="0 0 0"
"ActiveTitle"="10 36 106"
"TitleText"="255 255 255"
"InactiveTitle"="128 128 128"
"InactiveTitleText"="212 208 200"
"ButtonFace"="212 208 200"
"ButtonHilight"="255 255 255"
"ButtonShadow"="128 128 128"
"ButtonText"="0 0 0"
"GrayText"="128 128 128"
"Hilight"="10 36 106"
"HilightText"="255 255 255"

[HKEY_CURRENT_USER\Control Panel\Desktop\WindowMetrics]
"MinAnimate"="0"
"BorderWidth"="1"
"CaptionHeight"="-270"
"CaptionWidth"="-270"
"MenuHeight"="-270"
"MenuWidth"="-270"
"ScrollHeight"="-255"
"ScrollWidth"="-255"
EOF

# Apply Registry Changes
wine regedit /S /tmp/fonts.reg
wine regedit /S /tmp/theme.reg

rm /tmp/fonts.reg /tmp/theme.reg

# 3. X11 Cursor & Background Fix
if command -v xsetroot >/dev/null 2>&1; then
    # Set cursor to standard arrow and background to WineBot Blue
    xsetroot -cursor_name left_ptr -solid "#3A6EA5" || true
fi

echo "--> Theme applied."
