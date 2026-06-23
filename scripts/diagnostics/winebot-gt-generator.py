#!/usr/bin/env python3
"""WineBot Ground Truth Dataset Generator.

Generates perfectly labeled Wine desktop screenshots for training CV/OCR models.
Every pixel has known ground truth — zero manual annotation needed.

Output format:
  dataset/
    images/
      000001.png          # 1280x720 Wine desktop screenshot
      000002.png
    labels/
      000001.txt          # YOLO format: class_id cx cy w h (normalized)
      000002.txt
    ocr/
      000001.jsonl        # OCR ground truth: {"text": "Save", "bbox": [x,y,w,h], "confidence": 100}
    data.yaml             # YOLO dataset manifest

Usage:
  python3 winebot-gt-generator.py --output /models/wine-dataset --count 500

Classes (Wine-specific, extends ScreenParser's 55):
  0=TITLE_BAR, 1=TITLE_TEXT, 2=BUTTON, 3=CLOSE_BUTTON, 4=TEXT_FIELD,
  5=DROPDOWN, 6=CHECKBOX, 7=RADIO, 8=MENU_BAR, 9=MENU_ITEM,
  10=TASKBAR, 11=DIALOG, 12=TEXT_AREA, 13=SCROLLBAR, 14=LIST_ITEM,
  15=TAB, 16=PROGRESS_BAR, 17=TOOLBAR, 18=STATUS_BAR, 19=LINK,
  20=ICON, 21=SPINNER_BUTTON
"""

import argparse
import json
import os
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

# ── Wine Desktop Constants (tuned for Xvfb 1280x720) ──────────────────────

DESKTOP_SIZE = (1280, 720)
TASKBAR_HEIGHT = 32
TASKBAR_COLOR = (40, 40, 40)  # tint2 dark
TASKBAR_FONT_COLOR = (220, 220, 220)
TITLE_HEIGHT = 28
TITLE_COLOR = (0, 120, 215)  # Windows 10 blue
TITLE_TEXT_COLOR = (255, 255, 255)
WINDOW_BORDER = (180, 180, 180)
DESKTOP_BG = (58, 110, 165)  # Wine blue-gray desktop

# Wine-rendered fonts are softer than native Windows — add slight blur
WINE_SOFTNESS = 0.3  # Gaussian blur sigma

# ── YOLO class definitions ─────────────────────────────────────────────

WINE_CLASSES = [
    "title_bar",       # 0
    "title_text",      # 1
    "button",          # 2
    "close_button",    # 3
    "text_field",      # 4
    "dropdown",        # 5
    "checkbox",        # 6
    "radio",           # 7
    "menu_bar",        # 8
    "menu_item",       # 9
    "taskbar",         # 10
    "dialog",          # 11
    "text_area",       # 12
    "scrollbar",       # 13
    "list_item",       # 14
    "tab",             # 15
    "progress_bar",    # 16
    "toolbar",         # 17
    "status_bar",      # 18
    "link",            # 19
    "icon",            # 20
    "spinner_button",  # 21
]


@dataclass
class UIElement:
    cls_id: int
    bbox: List[int]  # [x, y, w, h]
    label: str = ""
    ocr_text: str = ""


@dataclass
class GeneratedPage:
    image: np.ndarray
    elements: List[UIElement] = field(default_factory=list)
    ground_truth_texts: List[Dict] = field(default_factory=list)


# ── Page generators ────────────────────────────────────────────────────

def draw_taskbar(img: np.ndarray) -> List[UIElement]:
    """Draw tint2 taskbar at bottom of desktop."""
    h, w = img.shape[:2]
    y = h - TASKBAR_HEIGHT
    cv2.rectangle(img, (0, y), (w, h), TASKBAR_COLOR, -1)

    # Taskbar buttons (simulated app icons)
    elems = []
    menu_items = ["Menu", "Browser", "Terminal", "Files", "Settings"]
    x = 10
    for item in menu_items:
        bw = random.randint(60, 100)
        cv2.rectangle(img, (x, y + 4), (x + bw, y + TASKBAR_HEIGHT - 4),
                      (60, 60, 60), -1)
        cv2.rectangle(img, (x, y + 4), (x + bw, y + TASKBAR_HEIGHT - 4),
                      (80, 80, 80), 1)
        tw = cv2.getTextSize(item, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)[0][0]
        cv2.putText(img, item, (x + (bw - tw) // 2, y + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, TASKBAR_FONT_COLOR, 1)
        elems.append(UIElement(10, [x, y + 4, bw, TASKBAR_HEIGHT - 8], "taskbar"))
        x += bw + 6

    # Clock area
    clock_text = "14:30"
    tw = cv2.getTextSize(clock_text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)[0][0]
    cv2.putText(img, clock_text, (w - tw - 16, y + 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, TASKBAR_FONT_COLOR, 1)

    elems.append(UIElement(10, [0, y, w, TASKBAR_HEIGHT], "taskbar"))
    return elems


def draw_window(img: np.ndarray, x: int, y: int, w: int, h: int,
                title: str = "Untitled", title_color=TITLE_COLOR,
                has_menu: bool = True, menu_items: List[str] = None) -> List[UIElement]:
    """Draw an application window with title bar, optional menu, and border."""
    elems = []

    # Window background
    cv2.rectangle(img, (x, y), (x + w, y + h), (240, 240, 240), -1)
    cv2.rectangle(img, (x, y), (x + w, y + h), WINDOW_BORDER, 1)

    # Title bar
    cv2.rectangle(img, (x, y), (x + w, y + TITLE_HEIGHT), title_color, -1)
    title_w = cv2.getTextSize(title, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 1)[0][0]
    cv2.putText(img, title, (x + 10, y + 21),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, TITLE_TEXT_COLOR, 1)
    elems.append(UIElement(0, [x, y, w, TITLE_HEIGHT], "title_bar"))
    elems.append(UIElement(1, [x + 10, y + 3, title_w + 4, TITLE_HEIGHT - 6],
                           "title_text", title))

    # Close button
    cx = x + w - 36
    cv2.rectangle(img, (cx, y + 4), (cx + 28, y + TITLE_HEIGHT - 4),
                  (200, 50, 50), -1)
    cv2.putText(img, "X", (cx + 9, y + 21),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    elems.append(UIElement(3, [cx, y + 4, 28, TITLE_HEIGHT - 8], "close_button"))

    # Menu bar
    if has_menu:
        menu_y = y + TITLE_HEIGHT
        cv2.rectangle(img, (x, menu_y), (x + w, menu_y + 22), (245, 245, 245), -1)
        items = menu_items or ["File", "Edit", "View", "Help"]
        mx = x + 8
        for item in items:
            tw = cv2.getTextSize(item, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0]
            elems.append(UIElement(9, [mx, menu_y, tw + 10, 22], "menu_item", item))
            cv2.putText(img, item, (mx + 5, menu_y + 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (30, 30, 30), 1)
            mx += tw + 14
        elems.append(UIElement(8, [x, menu_y, w, 22], "menu_bar"))

    return elems


def make_save_dialog() -> GeneratedPage:
    """Windows Save As dialog — the most common Wine interaction."""
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = DESKTOP_BG
    elems = []

    elems += draw_taskbar(img)

    # Dialog window
    dx, dy, dw, dh = 180, 90, 920, 540
    elems += draw_window(img, dx, dy, dw, dh, "Save As", has_menu=False)

    content_top = dy + TITLE_HEIGHT + 10

    # Sidebar with folder shortcuts
    sidebar_x = dx + 8
    sidebar_w = 170
    cv2.rectangle(img, (sidebar_x, content_top),
                  (sidebar_x + sidebar_w, dy + dh - 10), (230, 230, 230), -1)
    cv2.rectangle(img, (sidebar_x, content_top),
                  (sidebar_x + sidebar_w, dy + dh - 10), WINDOW_BORDER, 1)

    folders = ["Desktop", "Documents", "Downloads", "Music", "Pictures", "Videos"]
    for i, folder in enumerate(folders):
        fy = content_top + 8 + i * 30
        cv2.putText(img, folder, (sidebar_x + 8, fy + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (30, 30, 30), 1)
        elems.append(UIElement(14, [sidebar_x + 8, fy, sidebar_w - 16, 30],
                               "list_item", folder))

    # Right side: fields
    form_x = sidebar_x + sidebar_w + 16
    field_y = content_top + 8

    # File name field
    cv2.putText(img, "File name:", (form_x, field_y + 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50, 50, 50), 1)
    tf_x, tf_y = form_x + 100, field_y
    tf_w, tf_h = 400, 26
    cv2.rectangle(img, (tf_x, tf_y), (tf_x + tf_w, tf_y + tf_h), (255, 255, 255), -1)
    cv2.rectangle(img, (tf_x, tf_y), (tf_x + tf_w, tf_y + tf_h), (140, 140, 140), 1)
    default_name = random.choice(["document.txt", "report.pdf", "image.png",
                                   "data.csv", "backup.zip"])
    cv2.putText(img, default_name, (tf_x + 6, tf_y + 19),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    elems.append(UIElement(4, [tf_x, tf_y, tf_w, tf_h], "text_field", default_name))

    # Save as type dropdown
    dd_y = tf_y + tf_h + 18
    cv2.putText(img, "Save as type:", (form_x, dd_y + 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50, 50, 50), 1)
    dd_x = form_x + 100
    dd_w = 250
    cv2.rectangle(img, (dd_x, dd_y), (dd_x + dd_w, dd_y + 26), (255, 255, 255), -1)
    cv2.rectangle(img, (dd_x, dd_y), (dd_x + dd_w, dd_y + 26), (140, 140, 140), 1)
    cv2.putText(img, "Text Documents (*.txt)", (dd_x + 6, dd_y + 19),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
    # Dropdown arrow
    cv2.rectangle(img, (dd_x + dd_w - 22, dd_y + 2),
                  (dd_x + dd_w - 4, dd_y + 24), (220, 220, 220), -1)
    cv2.putText(img, "v", (dd_x + dd_w - 18, dd_y + 19),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50, 50, 50), 1)
    elems.append(UIElement(5, [dd_x, dd_y, dd_w, 26], "dropdown",
                           "Text Documents (*.txt)"))

    # File list area
    file_list_y = dd_y + 26 + 18
    file_list_h = 200
    cv2.rectangle(img, (form_x, file_list_y),
                  (form_x + 700, file_list_y + file_list_h), (255, 255, 255), -1)
    cv2.rectangle(img, (form_x, file_list_y),
                  (form_x + 700, file_list_y + file_list_h), (180, 180, 180), 1)

    files = ["notes.txt", "report_v2.pdf", "screenshot.png", "data_export.csv",
             "archive.zip", "README.md", "config.json"]
    for i, fname in enumerate(files):
        fy = file_list_y + 8 + i * 26
        cv2.putText(img, fname, (form_x + 8, fy + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 30), 1)
        elems.append(UIElement(14, [form_x + 8, fy, 700 - 16, 26],
                               "list_item", fname))

    # Scrollbar
    sb_x = form_x + 700 - 16
    cv2.rectangle(img, (sb_x, file_list_y), (sb_x + 16, file_list_y + file_list_h),
                  (230, 230, 230), -1)
    cv2.rectangle(img, (sb_x, file_list_y + 5), (sb_x + 16, file_list_y + 40),
                  (180, 180, 180), -1)
    cv2.rectangle(img, (sb_x, file_list_y + 5), (sb_x + 16, file_list_y + 40),
                  (150, 150, 150), 1)
    elems.append(UIElement(13, [sb_x, file_list_y, 16, file_list_h], "scrollbar"))

    # Action buttons
    btn_y = dy + dh - 46
    save_x = dx + dw - 320
    for bx, label, color in [
        (save_x, "Hide Folders", (200, 200, 200)),
        (save_x + 110, "Cancel", (200, 200, 200)),
        (save_x + 220, "Save", (0, 150, 0)),
    ]:
        bw, bh = 90, 30
        cv2.rectangle(img, (bx, btn_y), (bx + bw, btn_y + bh), color, -1)
        cv2.rectangle(img, (bx, btn_y), (bx + bw, btn_y + bh), (120, 120, 120), 1)
        tc = (255, 255, 255) if color == (0, 150, 0) else (50, 50, 50)
        tw = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0]
        cv2.putText(img, label, (bx + (bw - tw) // 2, btn_y + 21),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, tc, 1)
        elems.append(UIElement(2, [bx, btn_y, bw, bh], "button", label))

    return GeneratedPage(image=img, elements=elems)


def make_settings_window() -> GeneratedPage:
    """Settings/preferences dialog with tabs, checkboxes."""
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = DESKTOP_BG
    elems = []

    elems += draw_taskbar(img)

    wx, wy, ww, wh = 200, 70, 880, 580
    elems += draw_window(img, wx, wy, ww, wh, "Settings",
                         menu_items=["General", "Display", "Network", "Advanced"])

    content_top = wy + TITLE_HEIGHT + 22 + 10
    tab_y = content_top
    tabs = ["General", "Display", "Audio", "Network", "Advanced"]
    tx = wx + 16
    for tab in tabs:
        tw = cv2.getTextSize(tab, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0]
        cv2.rectangle(img, (tx, tab_y), (tx + tw + 14, tab_y + 24), (235, 235, 235), -1)
        cv2.rectangle(img, (tx, tab_y), (tx + tw + 14, tab_y + 24), (190, 190, 190), 1)
        cv2.putText(img, tab, (tx + 7, tab_y + 17),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (30, 30, 30), 1)
        elems.append(UIElement(15, [tx, tab_y, tw + 14, 24], "tab", tab))
        tx += tw + 20

    # Checkboxes
    checkboxes = [
        "Enable notifications",
        "Start with system",
        "Check for updates automatically",
        "Send usage statistics",
        "Enable debug logging",
    ]
    cb_y = tab_y + 50
    for i, cb_label in enumerate(checkboxes):
        by = cb_y + i * 34
        cb_x = wx + 30
        # Checkbox square
        cv2.rectangle(img, (cb_x, by), (cb_x + 18, by + 18), (255, 255, 255), -1)
        cv2.rectangle(img, (cb_x, by), (cb_x + 18, by + 18), (100, 100, 100), 2)
        if i % 2 == 0:  # Alternate checked/unchecked
            cv2.line(img, (cb_x + 3, by + 9), (cb_x + 8, by + 14), (0, 150, 0), 2)
            cv2.line(img, (cb_x + 8, by + 14), (cb_x + 16, by + 3), (0, 150, 0), 2)
        cv2.putText(img, cb_label, (cb_x + 28, by + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (30, 30, 30), 1)
        elems.append(UIElement(6, [cb_x, by, 18, 18], "checkbox", cb_label))

    # Radio buttons
    radio_y = cb_y + len(checkboxes) * 34 + 15
    cv2.putText(img, "Theme:", (wx + 30, radio_y - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50, 50, 50), 1)
    for i, theme in enumerate(["Light", "Dark", "System"]):
        rx = wx + 30 + i * 120
        cv2.circle(img, (rx, radio_y + 10), 8, (100, 100, 100), 1)
        if i == 0:  # Selected
            cv2.circle(img, (rx, radio_y + 10), 4, (0, 120, 215), -1)
        cv2.putText(img, theme, (rx + 16, radio_y + 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (30, 30, 30), 1)
        elems.append(UIElement(7, [rx - 8, radio_y + 2, 70, 18], "radio", theme))

    # Buttons
    btn_y = wy + wh - 46
    for bx, label, color in [
        (wx + ww - 310, "Reset to Defaults", (200, 200, 200)),
        (wx + ww - 200, "Cancel", (200, 200, 200)),
        (wx + ww - 100, "OK", (0, 120, 215)),
    ]:
        bw, bh = 90, 30
        cv2.rectangle(img, (bx, btn_y), (bx + bw, btn_y + bh), color, -1)
        cv2.rectangle(img, (bx, btn_y), (bx + bw, btn_y + bh), (120, 120, 120), 1)
        tc = (255, 255, 255) if color == (0, 120, 215) else (50, 50, 50)
        tw = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[0][0]
        cv2.putText(img, label, (bx + (bw - tw) // 2, btn_y + 21),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, tc, 1)
        elems.append(UIElement(2, [bx, btn_y, bw, bh], "button", label))

    return GeneratedPage(image=img, elements=elems)


def make_error_dialog() -> GeneratedPage:
    """Error/information popup dialog."""
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = DESKTOP_BG
    elems = []

    elems += draw_taskbar(img)

    # Centered small dialog
    dw, dh = 400, 180
    dx, dy = (DESKTOP_SIZE[0] - dw) // 2, (DESKTOP_SIZE[1] - dh) // 2
    cv2.rectangle(img, (dx, dy), (dx + dw, dy + dh), (255, 255, 255), -1)
    cv2.rectangle(img, (dx, dy), (dx + dw, dy + dh), WINDOW_BORDER, 2)

    # Title bar
    title = random.choice(["Error", "Warning", "Information", "Confirm"])
    if title == "Error":
        title_color_bg = (180, 30, 30)
    elif title == "Warning":
        title_color_bg = (200, 140, 0)
    else:
        title_color_bg = TITLE_COLOR

    cv2.rectangle(img, (dx, dy), (dx + dw, dy + TITLE_HEIGHT), title_color_bg, -1)
    cv2.putText(img, title, (dx + 10, dy + 21),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, TITLE_TEXT_COLOR, 1)
    elems.append(UIElement(0, [dx, dy, dw, TITLE_HEIGHT], "title_bar"))
    elems.append(UIElement(1, [dx + 10, dy + 4, 60, TITLE_HEIGHT - 8],
                           "title_text", title))

    # Close button
    cx = dx + dw - 36
    cv2.rectangle(img, (cx, dy + 4), (cx + 28, dy + TITLE_HEIGHT - 4),
                  (200, 50, 50), -1)
    cv2.putText(img, "X", (cx + 9, dy + 21),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    elems.append(UIElement(3, [cx, dy + 4, 28, TITLE_HEIGHT - 8], "close_button"))

    # Dialog icon
    icon_cx, icon_cy = dx + 35, dy + TITLE_HEIGHT + 36
    if title == "Error":
        cv2.circle(img, (icon_cx, icon_cy), 20, (200, 50, 50), 2)
        cv2.line(img, (icon_cx - 8, icon_cy - 8), (icon_cx + 8, icon_cy + 8), (200, 50, 50), 2)
        cv2.line(img, (icon_cx + 8, icon_cy - 8), (icon_cx - 8, icon_cy + 8), (200, 50, 50), 2)
    elif title == "Warning":
        cv2.putText(img, "!", (icon_cx - 12, icon_cy + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (200, 140, 0), 2)
    else:
        cv2.putText(img, "i", (icon_cx - 6, icon_cy + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 120, 215), 2)
    elems.append(UIElement(20, [icon_cx - 20, icon_cy - 20, 40, 40], "icon"))

    # Message text
    messages = {
        "Error": ("The operation could not be completed.", "Please try again."),
        "Warning": ("This action may have unintended consequences.", "Do you want to continue?"),
        "Information": ("The update was installed successfully.", "A restart may be required."),
        "Confirm": ("Are you sure you want to delete this file?", "This action cannot be undone."),
    }
    msg1, msg2 = messages[title]
    cv2.putText(img, msg1, (dx + 70, dy + TITLE_HEIGHT + 35),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    cv2.putText(img, msg2, (dx + 70, dy + TITLE_HEIGHT + 57),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (80, 80, 80), 1)
    elems.append(UIElement(11, [dx, dy, dw, dh], "dialog"))

    # Button
    btn_w, btn_h = 80, 28
    if title == "Confirm":
        # Yes + No
        for bx, label, btn_color in [
            (dx + dw - 190, "No", (200, 200, 200)),
            (dx + dw - 100, "Yes", (0, 120, 215)),
        ]:
            cv2.rectangle(img, (bx, dy + dh - 42), (bx + btn_w, dy + dh - 42 + btn_h), btn_color, -1)
            cv2.rectangle(img, (bx, dy + dh - 42), (bx + btn_w, dy + dh - 42 + btn_h), (120, 120, 120), 1)
            tw = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0]
            tc2 = (255, 255, 255) if btn_color != (200, 200, 200) else (50, 50, 50)
            cv2.putText(img, label, (bx + (btn_w - tw) // 2, dy + dh - 42 + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, tc2, 1)
            elems.append(UIElement(2, [bx, dy + dh - 42, btn_w, btn_h], "button", label))
    else:
        bx = dx + dw - 100
        cv2.rectangle(img, (bx, dy + dh - 42), (bx + btn_w, dy + dh - 42 + btn_h),
                      TITLE_COLOR, -1)
        cv2.rectangle(img, (bx, dy + dh - 42), (bx + btn_w, dy + dh - 42 + btn_h),
                      (0, 80, 160), 1)
        tw = cv2.getTextSize("OK", cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0]
        cv2.putText(img, "OK", (bx + (btn_w - tw) // 2, dy + dh - 42 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        elems.append(UIElement(2, [bx, dy + dh - 42, btn_w, btn_h], "button", "OK"))

    return GeneratedPage(image=img, elements=elems)


def make_notepad_window() -> GeneratedPage:
    """Notepad-style application with text content."""
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = DESKTOP_BG
    elems = []

    elems += draw_taskbar(img)

    wx, wy, ww, wh = 120, 50, 1040, 620
    elems += draw_window(img, wx, wy, ww, wh, "Untitled - Notepad",
                         menu_items=["File", "Edit", "Format", "View", "Help"])

    # Text area
    text_x = wx + 5
    text_y = wy + TITLE_HEIGHT + 22 + 3
    text_w = ww - 10
    text_h = wh - TITLE_HEIGHT - 22 - 8
    cv2.rectangle(img, (text_x, text_y), (text_x + text_w, text_y + text_h),
                  (255, 255, 255), -1)
    cv2.rectangle(img, (text_x, text_y), (text_x + text_w, text_y + text_h),
                  (200, 200, 200), 1)
    elems.append(UIElement(12, [text_x, text_y, text_w, text_h], "text_area"))

    # Scrollbar
    sb_x = wx + ww - 16
    cv2.rectangle(img, (sb_x, text_y), (sb_x + 16, text_y + text_h),
                  (230, 230, 230), -1)
    sb_thumb_h = int(text_h * 0.3)
    cv2.rectangle(img, (sb_x, text_y + 20), (sb_x + 16, text_y + 20 + sb_thumb_h),
                  (180, 180, 180), -1)
    cv2.rectangle(img, (sb_x, text_y + 20), (sb_x + 16, text_y + 20 + sb_thumb_h),
                  (150, 150, 150), 1)
    elems.append(UIElement(13, [sb_x, text_y, 16, text_h], "scrollbar"))

    # Sample text lines
    lines = [
        "Hello World!",
        "This is a test document created by WineBot.",
        "Perfect ground truth labels for every character.",
        "",
        "The quick brown fox jumps over the lazy dog.",
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "abcdefghijklmnopqrstuvwxyz",
        "0123456789 !@#$%^&*()",
        "",
        "WineBot CV/OCR Training Data Generator",
        "Version 1.0",
    ]
    for i, line in enumerate(lines):
        ly = text_y + 22 + i * 22
        cv2.putText(img, line, (text_x + 10, ly),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
        if line.strip():
            tw = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[0][0]
            elems.append(UIElement(14, [text_x + 10, ly - 16, tw, 20],
                                   "list_item", line))

    # Status bar
    sb_y = wy + wh - 20
    cv2.rectangle(img, (wx, sb_y), (wx + ww, sb_y + 20), (240, 240, 240), -1)
    cv2.rectangle(img, (wx, sb_y), (wx + ww, sb_y + 20), WINDOW_BORDER, 1)
    cv2.putText(img, "Ln 1, Col 1", (wx + 8, sb_y + 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (80, 80, 80), 1)
    elems.append(UIElement(18, [wx, sb_y, ww, 20], "status_bar"))

    return GeneratedPage(image=img, elements=elems)


def make_control_panel() -> GeneratedPage:
    """Dense control panel with toolbar, form fields, tables."""
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = DESKTOP_BG
    elems = []

    elems += draw_taskbar(img)

    wx, wy, ww, wh = 80, 40, 1120, 640
    elems += draw_window(img, wx, wy, ww, wh, "WineBot Control Panel",
                         menu_items=["File", "Tools", "View", "Help"])

    # Toolbar
    tb_y = wy + TITLE_HEIGHT + 22 + 3
    cv2.rectangle(img, (wx, tb_y), (wx + ww, tb_y + 30), (238, 238, 238), -1)
    tools = ["New", "Open", "Save", "|", "Cut", "Copy", "Paste", "|", "Start", "Stop"]
    tx = wx + 6
    for tool in tools:
        if tool == "|":
            cv2.line(img, (tx + 4, tb_y + 5), (tx + 4, tb_y + 25), (180, 180, 180), 1)
            tx += 10
            continue
        tw = cv2.getTextSize(tool, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)[0][0]
        bw = max(tw + 12, 40)
        cv2.rectangle(img, (tx, tb_y + 4), (tx + bw, tb_y + 26), (255, 255, 255), -1)
        cv2.rectangle(img, (tx, tb_y + 4), (tx + bw, tb_y + 26), (180, 180, 180), 1)
        cv2.putText(img, tool, (tx + (bw - tw) // 2, tb_y + 21),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (30, 30, 30), 1)
        elems.append(UIElement(17, [tx, tb_y + 4, bw, 26], "toolbar", tool))
        tx += bw + 4
    elems.append(UIElement(17, [wx, tb_y, ww, 30], "toolbar"))

    # Form content
    form_y = tb_y + 40
    form_x = wx + 20

    # Text fields with labels
    fields = [
        ("Session Name:", "winebot-session-2026"),
        ("API Endpoint:", "http://localhost:8000"),
        ("Auth Token:", "*" * 20),
        ("Recording Mode:", "Continuous"),
        ("Output Directory:", "/artifacts/sessions/"),
        ("Frame Rate:", "1.0 fps"),
    ]
    for i, (label, value) in enumerate(fields):
        fy = form_y + i * 36
        cv2.putText(img, label, (form_x, fy + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50, 50, 50), 1)
        tfw, tfh = 340, 24
        tfx = form_x + 160
        cv2.rectangle(img, (tfx, fy), (tfx + tfw, fy + tfh), (255, 255, 255), -1)
        cv2.rectangle(img, (tfx, fy), (tfx + tfw, fy + tfh), (150, 150, 150), 1)
        cv2.putText(img, value, (tfx + 6, fy + 17),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
        elems.append(UIElement(4, [tfx, fy, tfw, tfh], "text_field", value))

    # Start/Stop buttons
    btn_y = form_y + len(fields) * 36 + 16
    for bx, label, color in [
        (form_x, "Start Recording", (0, 160, 0)),
        (form_x + 150, "Stop Recording", (180, 50, 50)),
        (form_x + 300, "Reset", (180, 180, 180)),
    ]:
        bw, bh = 140, 34
        cv2.rectangle(img, (bx, btn_y), (bx + bw, btn_y + bh), color, -1)
        cv2.rectangle(img, (bx, btn_y), (bx + bw, btn_y + bh), (100, 100, 100), 1)
        tc = (255, 255, 255) if color != (180, 180, 180) else (30, 30, 30)
        tw = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0]
        cv2.putText(img, label, (bx + (bw - tw) // 2, btn_y + 23),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, tc, 1)
        elems.append(UIElement(2, [bx, btn_y, bw, bh], "button", label))

    # Progress bar
    pb_y = btn_y + 60
    cv2.putText(img, "Progress:", (form_x, pb_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50, 50, 50), 1)
    pb_x = form_x + 100
    pb_w = 400
    pb_h = 22
    cv2.rectangle(img, (pb_x, pb_y - 4), (pb_x + pb_w, pb_y + pb_h - 4), (230, 230, 230), -1)
    cv2.rectangle(img, (pb_x, pb_y - 4), (pb_x + pb_w, pb_y + pb_h - 4), (150, 150, 150), 1)
    fill_w = int(pb_w * 0.6)
    cv2.rectangle(img, (pb_x, pb_y - 4), (pb_x + fill_w, pb_y + pb_h - 4),
                  (0, 160, 0), -1)
    cv2.putText(img, "60%", (pb_x + pb_w // 2 - 15, pb_y + 13),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
    elems.append(UIElement(16, [pb_x, pb_y - 4, pb_w, pb_h], "progress_bar"))

    return GeneratedPage(image=img, elements=elems)


# ── Generator registry ──────────────────────────────────────────────────

GENERATORS = [
    ("save_dialog", make_save_dialog),
    ("settings", make_settings_window),
    ("error_dialog", make_error_dialog),
    ("notepad", make_notepad_window),
    ("control_panel", make_control_panel),
]


# ── Output methods ──────────────────────────────────────────────────────

def yolo_label(element: UIElement, img_w: int, img_h: int) -> str:
    """Convert UIElement to YOLO format string."""
    x, y, bw, bh = element.bbox
    cx = (x + bw / 2) / img_w
    cy = (y + bh / 2) / img_h
    nw = bw / img_w
    nh = bh / img_h
    return f"{element.cls_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}"


def add_wine_softness(img: np.ndarray) -> np.ndarray:
    """Add subtle blur to simulate Wine's softer font rendering."""
    if random.random() < 0.7:  # 70% chance
        sigma = random.uniform(0.1, 0.4)
        img = cv2.GaussianBlur(img, (3, 3), sigma)
    return img


def add_noise(img: np.ndarray) -> np.ndarray:
    """Add subtle noise to simulate compression artifacts."""
    noise = np.random.normal(0, 2, img.shape).astype(np.int16)
    img = img.astype(np.int16) + noise
    return np.clip(img, 0, 255).astype(np.uint8)


def variation(img: np.ndarray) -> np.ndarray:
    """Apply random variations to increase dataset diversity."""
    # Brightness
    if random.random() < 0.3:
        delta = random.randint(-20, 20)
        img = cv2.convertScaleAbs(img, alpha=1, beta=delta)
    # Contrast
    if random.random() < 0.2:
        alpha = random.uniform(0.85, 1.15)
        img = cv2.convertScaleAbs(img, alpha=alpha, beta=0)
    return img


def dict_name(name: str, prefix: str, suffix: str) -> str:
    """Convert snake_case to display text: save_dialog -> Save Dialog."""
    return name.replace("_", " ").title()


# ── Main generator ──────────────────────────────────────────────────────

def generate_dataset(output_dir: str, count: int, seed: int = 42):
    """Generate a full labeled dataset."""
    random.seed(seed)
    np.random.seed(seed)

    img_dir = os.path.join(output_dir, "images")
    lbl_dir = os.path.join(output_dir, "labels")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(lbl_dir, exist_ok=True)

    manifest = {"classes": WINE_CLASSES, "images": []}
    ocr_entries = []

    per_generator = max(1, count // len(GENERATORS))
    img_idx = 0

    for gen_name, gen_fn in GENERATORS:
        for i in range(per_generator):
            page = gen_fn()

            # Apply Wine rendering variations
            img = page.image.astype(np.float32)
            if WINE_SOFTNESS > 0:
                img = cv2.GaussianBlur(img, (3, 3), WINE_SOFTNESS)
            img = add_noise(img.astype(np.uint8))
            img = variation(img)

            h, w = img.shape[:2]

            # Save image
            img_name = f"{img_idx:06d}.png"
            img_path = os.path.join(img_dir, img_name)
            cv2.imwrite(img_path, img)

            # Save YOLO labels
            lbl_path = os.path.join(lbl_dir, f"{img_idx:06d}.txt")
            with open(lbl_path, "w") as f:
                for elem in page.elements:
                    f.write(yolo_label(elem, w, h) + "\n")

            # Collect OCR ground truth
            for elem in page.elements:
                if elem.ocr_text:
                    ocr_entries.append({
                        "image": img_name,
                        "text": elem.ocr_text,
                        "bbox": elem.bbox,
                        "class": WINE_CLASSES[elem.cls_id],
                        "confidence": 100,  # Perfect ground truth
                    })

            manifest["images"].append({
                "file": img_name,
                "generator": gen_name,
                "elements": len(page.elements),
                "ocr_texts": sum(1 for e in page.elements if e.ocr_text),
            })

            img_idx += 1
            if img_idx % 50 == 0:
                print(f"  {img_idx}/{count} images...")

    # Write data.yaml for YOLO training
    yaml_path = os.path.join(output_dir, "data.yaml")
    with open(yaml_path, "w") as f:
        f.write(f"# WineBot Ground Truth Dataset — {img_idx} images\n")
        f.write(f"path: {output_dir}\n")
        f.write(f"train: images\n")
        f.write(f"val: images\n")
        f.write(f"nc: {len(WINE_CLASSES)}\n")
        f.write("names:\n")
        for i, name in enumerate(WINE_CLASSES):
            f.write(f"  {i}: {name}\n")

    # Write OCR ground truth
    ocr_path = os.path.join(output_dir, "ocr_ground_truth.jsonl")
    with open(ocr_path, "w") as f:
        for entry in ocr_entries:
            f.write(json.dumps(entry) + "\n")

    # Write manifest
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nDataset generated: {img_idx} images")
    print(f"  Images: {img_dir}/")
    print(f"  Labels: {lbl_dir}/")
    print(f"  Config: {yaml_path}")
    print(f"  OCR GT: {ocr_path}")
    print(f"  Total elements: {sum(m['elements'] for m in manifest['images'])}")
    print(f"  OCR annotations: {len(ocr_entries)}")

    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="WineBot Ground Truth Dataset Generator"
    )
    parser.add_argument("--output", default="/models/wine-dataset",
                        help="Output directory for dataset")
    parser.add_argument("--count", type=int, default=500,
                        help="Number of images to generate")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility")
    args = parser.parse_args()

    print(f"WineBot Ground Truth Generator")
    print(f"  Output: {args.output}")
    print(f"  Images: {args.count}")
    print(f"  Classes: {len(WINE_CLASSES)}")
    print(f"  Generators: {len(GENERATORS)}")
    print()

    generate_dataset(args.output, args.count, args.seed)


if __name__ == "__main__":
    main()
