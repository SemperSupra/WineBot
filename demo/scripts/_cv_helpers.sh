#!/bin/bash
# CV + OCR helpers for demo scripts
# Uses Tesseract OCR (built-in) to find UI elements instead of hardcoded coords.

# Find a UI element by text label and return its click center coordinates
# Usage: cv_find_button "Save" → "410,337"
cv_find_button() {
  local label="$1"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
    python3 -c \"
import subprocess, json, sys
subprocess.run(['import', '-window', 'root', '/tmp/cv_btn.png'], capture_output=True, timeout=5)
import pytesseract
try:
    data = pytesseract.image_to_data('/tmp/cv_btn.png', output_type=pytesseract.Output.DICT)
    for i in range(len(data['text'])):
        text = data['text'][i].strip()
        if text and '$label' in text:
            x = data['left'][i] + data['width'][i] // 2
            y = data['top'][i] + data['height'][i] // 2
            print(f'{x},{y}')
            sys.exit(0)
    print('')
except: print('')
\"
  " 2>/dev/null || echo ""
}

# Find a window by title substring, return its bounding box
# Usage: cv_find_window "Save As" → "5,43,557,355"
cv_find_window() {
  local title="$1"
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 sh -c "
    python3 -c \"
import subprocess, pytesseract, cv2, numpy as np
subprocess.run(['import', '-window', 'root', '/tmp/cv_win.png'], capture_output=True, timeout=5)
img = cv2.imread('/tmp/cv_win.png')
if img is None: sys.exit(0)
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 5)
contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
for cnt in contours:
    x, y, w, h = cv2.boundingRect(cnt)
    if w < 200 or h < 80 or h > 600: continue
    roi = img[y:y+30, x:x+w]
    if roi.size > 0:
        try:
            txt = pytesseract.image_to_string(roi, config='--psm 7').strip()
            if '$title' in txt:
                print(f'{x},{y},{w},{h}')
                sys.exit(0)
        except: pass
print('')
\"
  " 2>/dev/null || echo ""
}

# Find all clickable elements and return their coordinates with labels
# Usage: cv_detect_elements → JSON list
cv_detect_elements() {
  MSYS_NO_PATHCONV=1 docker exec compose-winebot-interactive-1 python3 \
    /scripts/diagnostics/cv-element-detect.py --screenshot --label "demo" 2>/dev/null || echo "{}"
}

# Find a click target from the element detector JSON output
# Usage: cv_click_target "Save" → "410,337"
cv_click_target() {
  local label="$1"
  local json
  json=$(cv_detect_elements)
  if [ "$json" = "{}" ] || [ -z "$json" ]; then
    echo ""
    return
  fi
  echo "$json" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for t in d.get('key_text', []):
    if '$label'.lower() in t.lower():
        print('found')  # just signal existence
" 2>/dev/null || echo ""
}
