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

import cv2
import numpy as np

# ── Wine Desktop Constants (tuned for Xvfb 1280x720) ──────────────────────

DESKTOP_SIZE = (1280, 720)

# Multi-framework UI theme system.
# Each framework renders widgets differently — title bar height, colors,
# button shapes, font sizes, border styles. We sample randomly to train
# a model that generalizes across Qt, Gtk, Win32, Java Swing, Tk, and
# Electron/web UI frameworks running under Wine.

FRAMEWORK_THEMES = {
    "win32_classic": {
        "title_height": 28, "title_color": (0, 120, 215),
        "title_text_color": (255, 255, 255), "title_font_scale": 0.65,
        "button_color": (225, 225, 225), "button_text_color": (0, 0, 0),
        "button_border_3d": True, "window_bg": (240, 240, 240),
        "menu_bg": (245, 245, 245), "font_face": cv2.FONT_HERSHEY_SIMPLEX,
        "checkbox_style": "checkmark",
    },
    "win10_fluent": {
        "title_height": 30, "title_color": (0, 120, 215),
        "title_text_color": (255, 255, 255), "title_font_scale": 0.60,
        "button_color": (0, 120, 215), "button_text_color": (255, 255, 255),
        "button_border_3d": False, "window_bg": (255, 255, 255),
        "menu_bg": (240, 240, 240), "font_face": cv2.FONT_HERSHEY_SIMPLEX,
        "checkbox_style": "checkmark",
    },
    "qt_fusion": {
        "title_height": 30, "title_color": (50, 50, 50),
        "title_text_color": (220, 220, 220), "title_font_scale": 0.60,
        "button_color": (65, 65, 65), "button_text_color": (220, 220, 220),
        "button_border_3d": False, "window_bg": (45, 45, 45),
        "menu_bg": (55, 55, 55), "font_face": cv2.FONT_HERSHEY_SIMPLEX,
        "checkbox_style": "checkmark",
    },
    "gtk_adwaita": {
        "title_height": 26, "title_color": (42, 42, 42),
        "title_text_color": (230, 230, 230), "title_font_scale": 0.60,
        "button_color": (230, 230, 230), "button_text_color": (20, 20, 20),
        "button_border_3d": False, "window_bg": (250, 250, 250),
        "menu_bg": (240, 240, 240), "font_face": cv2.FONT_HERSHEY_SIMPLEX,
        "checkbox_style": "checkmark",
    },
    "java_metal": {
        "title_height": 24, "title_color": (128, 128, 128),
        "title_text_color": (255, 255, 255), "title_font_scale": 0.55,
        "button_color": (200, 200, 200), "button_text_color": (0, 0, 0),
        "button_border_3d": True, "window_bg": (238, 238, 238),
        "menu_bg": (238, 238, 238), "font_face": cv2.FONT_HERSHEY_SIMPLEX,
        "checkbox_style": "checkmark",
    },
    "tkinter": {
        "title_height": 20, "title_color": (200, 50, 50),
        "title_text_color": (255, 255, 255), "title_font_scale": 0.50,
        "button_color": (220, 220, 220), "button_text_color": (0, 0, 0),
        "button_border_3d": True, "window_bg": (240, 240, 240),
        "menu_bg": (240, 240, 240), "font_face": cv2.FONT_HERSHEY_SIMPLEX,
        "checkbox_style": "checkmark",
    },
    "electron_dark": {
        "title_height": 32, "title_color": (30, 30, 30),
        "title_text_color": (220, 220, 220), "title_font_scale": 0.55,
        "button_color": (60, 60, 60), "button_text_color": (220, 220, 220),
        "button_border_3d": False, "window_bg": (35, 35, 35),
        "menu_bg": (45, 45, 45), "font_face": cv2.FONT_HERSHEY_SIMPLEX,
        "checkbox_style": "toggle",
    },
    "classic_95": {
        "title_height": 18, "title_color": (0, 0, 128),
        "title_text_color": (255, 255, 255), "title_font_scale": 0.55,
        "button_color": (192, 192, 192), "button_text_color": (0, 0, 0),
        "button_border_3d": True, "window_bg": (192, 192, 192),
        "menu_bg": (192, 192, 192), "font_face": cv2.FONT_HERSHEY_SIMPLEX,
        "checkbox_style": "checkmark",
    },
}


# ── Split Definitions ─────────────────────────────────────────────────────

TRAIN_SCENES = [
    "save_dialog", "settings", "error_dialog", "notepad",
    "control_panel", "file_manager", "multi_window", "browser",
    "terminal", "context_menu", "wizard", "find_replace", "print_dialog",
]
VAL_SCENES = ["about_dialog", "file_properties"]
TEST_SCENES = ["system_tray", "form_fill"]

TRAIN_FRAMEWORKS = [
    "win32_classic", "win10_fluent", "qt_fusion",
    "gtk_adwaita", "java_metal", "tkinter",
]
TEST_FRAMEWORKS = ["electron_dark", "classic_95"]


def _get_split_scenes(split: str) -> list[str]:
    if split == "train":
        return TRAIN_SCENES
    elif split == "val":
        return VAL_SCENES
    elif split == "test":
        return TEST_SCENES
    return TRAIN_SCENES + VAL_SCENES + TEST_SCENES  # "all"


def _get_split_frameworks(split: str) -> list[dict]:
    """Return the list of framework theme dicts for this split."""
    if split in ("val", "test"):
        # Val/test use held-out frameworks
        names = TEST_FRAMEWORKS
    else:
        names = TRAIN_FRAMEWORKS
    return [FRAMEWORK_THEMES[n] for n in names if n in FRAMEWORK_THEMES]


_CURRENT_SPLIT = "train"


def set_split(split: str):
    """Set the current split for theme sampling."""
    global _CURRENT_SPLIT
    _CURRENT_SPLIT = split


def sample_theme() -> dict:
    """Randomly sample a UI framework theme with jitter.

    Uses the current split (set via set_split()) to determine which
    frameworks are available. Call set_split("test") before generating
    test-set images to use held-out frameworks only.
    """
    frameworks = _get_split_frameworks(_CURRENT_SPLIT)
    theme = random.choice(frameworks).copy()
    # Jitter colors slightly
    for key in ["title_color", "button_color", "window_bg", "menu_bg"]:
        if key in theme:
            c = list(theme[key])
            c = [min(255, max(0, v + random.randint(-15, 15))) for v in c]
            theme[key] = tuple(c)
    # Jitter title height
    theme["title_height"] += random.randint(-2, 4)
    return theme


TASKBAR_HEIGHT = 32
TASKBAR_THEMES = [
    {"color": (40, 40, 40), "font_color": (220, 220, 220)},   # tint2 dark
    {"color": (30, 30, 50), "font_color": (200, 200, 220)},   # dark blue
    {"color": (60, 60, 60), "font_color": (240, 240, 240)},   # dark gray
    {"color": (25, 25, 30), "font_color": (200, 200, 200)},   # near-black
]
DESKTOP_BG_THEMES = [
    (58, 110, 165),   # Wine blue-gray
    (30, 30, 50),     # dark
    (100, 120, 140),  # gray-blue
    (40, 60, 80),     # steel
    (20, 40, 60),     # dark blue
]

WINDOW_BORDER = (180, 180, 180)
WINE_SOFTNESS = 0.3

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
    bbox: list[int]  # [x, y, w, h]
    label: str = ""
    ocr_text: str = ""


@dataclass
class GeneratedPage:
    image: np.ndarray
    elements: list[UIElement] = field(default_factory=list)
    ground_truth_texts: list[dict] = field(default_factory=list)


# Font face randomization for cross-rendering robustness
AVAILABLE_FONTS = [
    cv2.FONT_HERSHEY_SIMPLEX,
    cv2.FONT_HERSHEY_DUPLEX,
    cv2.FONT_HERSHEY_COMPLEX,
    cv2.FONT_HERSHEY_COMPLEX_SMALL,
    cv2.FONT_HERSHEY_TRIPLEX,
]

def get_font():
    """Random font face with scale/thickness jitter."""
    font = random.choice(AVAILABLE_FONTS)
    scale = random.uniform(0.85, 1.15)
    thickness = random.choice([1, 1, 1, 2])
    return font, scale, thickness

# Window state enumeration for generalization
WINDOW_STATES = ["active"] * 6 + ["inactive"] * 2 + ["maximized"] * 1 + ["minimized"] * 1

def apply_window_state(img, elements, x, y, w, h, state, theme):
    """Modify elements for different window states. Returns adjusted element list."""
    if state == "active":
        return elements  # No change
    elif state == "inactive":
        # Dim the title bar and window content
        overlay = img[y:y+h, x:x+w].copy()
        overlay = cv2.convertScaleAbs(overlay, alpha=0.7, beta=20)
        img[y:y+h, x:x+w] = overlay
        # Mark elements as potentially less interactive
        for e in elements:
            if e.cls_id in (0, 1, 3):  # title bar elements
                pass  # Still visible
        return elements
    elif state == "maximized":
        # Fill entire desktop area (no borders on edge)
        # Already rendered at full size — just remove window border elements
        return [e for e in elements if e.cls_id not in (0,)]
    elif state == "minimized":
        # Only shows in taskbar — return only taskbar elements
        return [e for e in elements if e.cls_id == 10]

def draw_modal_overlay(img, active_rect=None):
    """Draw semi-transparent dimmed overlay behind a modal dialog."""
    overlay = img.copy()
    cv2.rectangle(overlay, (0, 0), (img.shape[1], img.shape[0]), (80, 80, 80), -1)
    alpha = 0.4
    if active_rect:
        x, y, w, h = active_rect
        cv2.rectangle(overlay, (x, y), (x + w, y + h), (255, 255, 255), -1)
        alpha = 0.35
    return cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0)


# ── Page generators ────────────────────────────────────────────────────

def draw_taskbar(img: np.ndarray) -> list[UIElement]:
    """Draw a tint2-style taskbar at bottom. Theme varies randomly."""
    h, w = img.shape[:2]
    y = h - TASKBAR_HEIGHT
    theme = random.choice(TASKBAR_THEMES)
    cv2.rectangle(img, (0, y), (w, h), theme["color"], -1)
    elems = []
    menu_items = ["Menu", "Browser", "Terminal", "Files", "Settings"]
    x = 10
    for item in menu_items:
        bw = random.randint(60, 100)
        btn_color = tuple(min(255, max(0, c + random.randint(-15, 15)))
                          for c in theme["color"])
        cv2.rectangle(img, (x, y + 4), (x + bw, y + TASKBAR_HEIGHT - 4), btn_color, -1)
        cv2.rectangle(img, (x, y + 4), (x + bw, y + TASKBAR_HEIGHT - 4),
                      tuple(min(255, c + 20) for c in btn_color), 1)
        tw = cv2.getTextSize(item, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)[0][0]
        cv2.putText(img, item, (x + (bw - tw) // 2, y + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, theme["font_color"], 1)
        elems.append(UIElement(10, [x, y + 4, bw, TASKBAR_HEIGHT - 8], "taskbar"))
        x += bw + 6
    clock_text = f"{random.randint(0,23):02d}:{random.randint(0,59):02d}"
    tw = cv2.getTextSize(clock_text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)[0][0]
    cv2.putText(img, clock_text, (w - tw - 16, y + 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, theme["font_color"], 1)
    elems.append(UIElement(10, [0, y, w, TASKBAR_HEIGHT], "taskbar"))
    return elems


def draw_window(img: np.ndarray, x: int, y: int, w: int, h: int,
                title: str = "Untitled", theme: dict = None,
                has_menu: bool = True, menu_items: list[str] = None) -> list[UIElement]:
    """Draw an application window with framework-specific title bar and chrome.

    Args:
        theme: Framework visual style from FRAMEWORK_THEMES. If None, sampled randomly.
    """
    if theme is None:
        theme = sample_theme()
    elems = []
    title_h = theme["title_height"]

    # Window background
    bg = theme["window_bg"]
    cv2.rectangle(img, (x, y), (x + w, y + h), bg, -1)
    cv2.rectangle(img, (x, y), (x + w, y + h), WINDOW_BORDER, 1)

    # Title bar
    cv2.rectangle(img, (x, y), (x + w, y + title_h), theme["title_color"], -1)
    title_w = cv2.getTextSize(title, theme["font_face"], theme["title_font_scale"], 1)[0][0]
    cv2.putText(img, title, (x + 10, y + title_h - 7),
                theme["font_face"], theme["title_font_scale"], theme["title_text_color"], 1)
    elems.append(UIElement(0, [x, y, w, title_h], "title_bar"))
    elems.append(UIElement(1, [x + 10, y + 3, title_w + 4, title_h - 6],
                           "title_text", title))

    # Close button — varies by framework
    cx = x + w - 36
    close_color = (200, 50, 50) if theme.get("button_border_3d") else (220, 60, 60)
    cv2.rectangle(img, (cx, y + 4), (cx + 28, y + title_h - 4), close_color, -1)
    if theme.get("button_border_3d"):
        cv2.rectangle(img, (cx, y + 4), (cx + 28, y + title_h - 4), (150, 30, 30), 1)
    cv2.putText(img, "X", (cx + 9, y + title_h - 9),
                theme["font_face"], 0.5, (255, 255, 255), 1)
    elems.append(UIElement(3, [cx, y + 4, 28, title_h - 8], "close_button"))

    # Menu bar
    if has_menu:
        menu_y = y + title_h
        cv2.rectangle(img, (x, menu_y), (x + w, menu_y + 22), theme["menu_bg"], -1)
        cv2.rectangle(img, (x, menu_y), (x + w, menu_y + 22), WINDOW_BORDER, 1)
        items = menu_items or ["File", "Edit", "View", "Help"]
        mx = x + 8
        for item in items:
            tw = cv2.getTextSize(item, theme["font_face"], 0.45, 1)[0][0]
            elems.append(UIElement(9, [mx, menu_y, tw + 10, 22], "menu_item", item))
            cv2.putText(img, item, (mx + 5, menu_y + 15),
                        theme["font_face"], 0.45, (20, 20, 20), 1)
            mx += tw + 14
        elems.append(UIElement(8, [x, menu_y, w, 22], "menu_bar"))

    return elems



def draw_button(img, x, y, w, h, label, theme, primary=False):
    """Draw a framework-themed button."""
    if primary:
        color = theme["title_color"]  # Accent color for primary actions
        text_color = (255, 255, 255)
    else:
        color = theme["button_color"]
        text_color = theme["button_text_color"]
    if theme.get("button_border_3d"):
        # 3D bevel
        cv2.rectangle(img, (x, y), (x + w, y + h), color, -1)
        cv2.rectangle(img, (x, y), (x + w, y + h), (255, 255, 255), 1)  # top-left highlight
        cv2.rectangle(img, (x + 1, y + 1), (x + w - 1, y + h - 1), (100, 100, 100), 1)  # bottom-right shadow
    else:
        cv2.rectangle(img, (x, y), (x + w, y + h), color, -1)
        cv2.rectangle(img, (x, y), (x + w, y + h),
                      tuple(min(255, c + 30) for c in color), 1)
    fs = theme["title_font_scale"] - 0.05
    tw = cv2.getTextSize(label, theme["font_face"], fs, 1)[0][0]
    cv2.putText(img, label, (x + (w - tw) // 2, y + h - 8),
                theme["font_face"], fs, text_color, 1)
    return UIElement(2, [x, y, w, h], "button", label)


def make_save_dialog() -> GeneratedPage:
    """Windows Save As dialog — the most common Wine interaction."""
    theme = sample_theme()
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = []

    elems += draw_taskbar(img)

    # Dialog window
    dx, dy, dw, dh = 180, 90, 920, 540
    elems += draw_window(img, dx, dy, dw, dh, "Save As", theme=theme, has_menu=False)

    content_top = dy + theme["title_height"] + 10

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
    elems.append(draw_button(img, save_x, btn_y, 90, 30, "Hide Folders", theme))
    elems.append(draw_button(img, save_x + 110, btn_y, 90, 30, "Cancel", theme))
    elems.append(draw_button(img, save_x + 220, btn_y, 90, 30, "Save", theme, primary=True))

    return GeneratedPage(image=img, elements=elems)


def make_settings_window() -> GeneratedPage:
    """Settings/preferences dialog with tabs, checkboxes."""
    theme = sample_theme()
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = []

    elems += draw_taskbar(img)

    wx, wy, ww, wh = 200, 70, 880, 580
    elems += draw_window(img, wx, wy, ww, wh, "Settings", theme=theme,
                         menu_items=["General", "Display", "Network", "Advanced"])

    content_top = wy + theme["title_height"] + 22 + 10
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
    for i, theme_name in enumerate(["Light", "Dark", "System"]):
        rx = wx + 30 + i * 120
        cv2.circle(img, (rx, radio_y + 10), 8, (100, 100, 100), 1)
        if i == 0:  # Selected
            cv2.circle(img, (rx, radio_y + 10), 4, (0, 120, 215), -1)
        cv2.putText(img, theme_name, (rx + 16, radio_y + 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (30, 30, 30), 1)
        elems.append(UIElement(7, [rx - 8, radio_y + 2, 70, 18], "radio", theme_name))

    # Buttons
    btn_y = wy + wh - 46
    elems.append(draw_button(img, wx + ww - 310, btn_y, 90, 30, "Reset to Defaults", theme))
    elems.append(draw_button(img, wx + ww - 200, btn_y, 90, 30, "Cancel", theme))
    elems.append(draw_button(img, wx + ww - 100, btn_y, 90, 30, "OK", theme, primary=True))

    return GeneratedPage(image=img, elements=elems)


def make_error_dialog() -> GeneratedPage:
    """Error/information popup dialog."""
    theme = sample_theme()
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = random.choice(DESKTOP_BG_THEMES)
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
        title_color_bg = theme["title_color"]

    title_h = theme["title_height"]
    cv2.rectangle(img, (dx, dy), (dx + dw, dy + title_h), title_color_bg, -1)
    cv2.putText(img, title, (dx + 10, dy + title_h - 7),
                theme["font_face"], theme["title_font_scale"], theme["title_text_color"], 1)
    elems.append(UIElement(0, [dx, dy, dw, title_h], "title_bar"))
    elems.append(UIElement(1, [dx + 10, dy + 4, 60, title_h - 8],
                           "title_text", title))

    # Close button
    cx = dx + dw - 36
    cv2.rectangle(img, (cx, dy + 4), (cx + 28, dy + title_h - 4), (200, 50, 50), -1)
    cv2.putText(img, "X", (cx + 9, dy + title_h - 9),
                theme["font_face"], 0.5, (255, 255, 255), 1)
    elems.append(UIElement(3, [cx, dy + 4, 28, title_h - 8], "close_button"))

    # Dialog icon
    icon_cx, icon_cy = dx + 35, dy + theme["title_height"] + 36
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
    cv2.putText(img, msg1, (dx + 70, dy + theme["title_height"] + 35),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    cv2.putText(img, msg2, (dx + 70, dy + theme["title_height"] + 57),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (80, 80, 80), 1)
    elems.append(UIElement(11, [dx, dy, dw, dh], "dialog"))

    # Buttons
    if title == "Confirm":
        elems.append(draw_button(img, dx + dw - 190, dy + dh - 42, 80, 28, "No", theme))
        elems.append(draw_button(img, dx + dw - 100, dy + dh - 42, 80, 28, "Yes", theme, primary=True))
    else:
        elems.append(draw_button(img, dx + dw - 100, dy + dh - 42, 80, 28, "OK", theme, primary=True))

    return GeneratedPage(image=img, elements=elems)


def make_notepad_window() -> GeneratedPage:
    """Notepad-style application with text content."""
    theme = sample_theme()
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = []

    elems += draw_taskbar(img)

    wx, wy, ww, wh = 120, 50, 1040, 620
    elems += draw_window(img, wx, wy, ww, wh, "Untitled - Notepad", theme=theme,
                         menu_items=["File", "Edit", "Format", "View", "Help"])

    # Text area
    text_x = wx + 5
    text_y = wy + theme["title_height"] + 22 + 3
    text_w = ww - 10
    text_h = wh - theme["title_height"] - 22 - 8
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
    ocr_texts = []
    for i, line in enumerate(lines):
        ly = text_y + 22 + i * 22
        cv2.putText(img, line, (text_x + 10, ly),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
        # Content lines — OCR ground truth only, NOT YOLO UI elements.
        # The text_area (class 12) is the structural element.
        if line.strip():
            tw = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[0][0]
            ocr_texts.append({
                "text": line,
                "bbox": [text_x + 10, ly - 16, tw, 20],
            })

    # Status bar
    sb_y = wy + wh - 20
    cv2.rectangle(img, (wx, sb_y), (wx + ww, sb_y + 20), (240, 240, 240), -1)
    cv2.rectangle(img, (wx, sb_y), (wx + ww, sb_y + 20), WINDOW_BORDER, 1)
    status_text = f"Ln {random.randint(1,20)}, Col {random.randint(1,80)}"
    cv2.putText(img, status_text, (wx + 8, sb_y + 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (80, 80, 80), 1)
    elems.append(UIElement(18, [wx, sb_y, ww, 20], "status_bar", status_text))

    return GeneratedPage(image=img, elements=elems, ground_truth_texts=ocr_texts)


def make_control_panel() -> GeneratedPage:
    """Dense control panel with toolbar, form fields, tables."""
    theme = sample_theme()
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = []

    elems += draw_taskbar(img)

    wx, wy, ww, wh = 80, 40, 1120, 640
    elems += draw_window(img, wx, wy, ww, wh, "WineBot Control Panel", theme=theme,
                         menu_items=["File", "Tools", "View", "Help"])

    # Toolbar
    tb_y = wy + theme["title_height"] + 22 + 3
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
    elems.append(draw_button(img, form_x, btn_y, 140, 34, "Start Recording", theme, primary=True))
    elems.append(draw_button(img, form_x + 150, btn_y, 140, 34, "Stop Recording", theme))
    elems.append(draw_button(img, form_x + 300, btn_y, 140, 34, "Reset", theme))

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


# ── New scenes (Rung 4) ─────────────────────────────────────────────────

def make_browser() -> GeneratedPage:
    """Web browser window with tabs, address bar, bookmarks toolbar, content area."""
    theme = sample_theme()
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = draw_taskbar(img)
    wx, wy, ww, wh = 60, 40, 1160, 640
    elems += draw_window(img, wx, wy, ww, wh, "WineBot Browser", theme=theme,
                         menu_items=["File", "Edit", "View", "History", "Bookmarks", "Help"])

    tab_bar_y = wy + theme["title_height"] + 22 + 4
    tabs = ["Home", "Documentation", "GitHub"]
    tx = wx + 4
    for j, tab in enumerate(tabs):
        tw = cv2.getTextSize(tab, theme["font_face"], 0.4, 1)[0][0]
        bw = tw + 20
        bg_color = (255, 255, 255) if j == 0 else (225, 225, 225)
        cv2.rectangle(img, (tx, tab_bar_y), (tx + bw, tab_bar_y + 28), bg_color, -1)
        cv2.rectangle(img, (tx, tab_bar_y), (tx + bw, tab_bar_y + 28), (180, 180, 180), 1)
        cv2.putText(img, tab, (tx + 10, tab_bar_y + 19), theme["font_face"], 0.4, (30, 30, 30), 1)
        elems.append(UIElement(15, [tx, tab_bar_y, bw, 28], "tab", tab))
        tx += bw + 1

    # Address bar
    addr_y = tab_bar_y + 34
    cv2.rectangle(img, (wx + 4, addr_y), (wx + ww - 8, addr_y + 26), (255, 255, 255), -1)
    cv2.rectangle(img, (wx + 4, addr_y), (wx + ww - 8, addr_y + 26), (160, 160, 160), 1)
    url = "https://winebot.local/docs/getting-started"
    cv2.putText(img, url, (wx + 12, addr_y + 18), theme["font_face"], 0.4, (0, 0, 0), 1)
    elems.append(UIElement(4, [wx + 4, addr_y, ww - 8, 26], "text_field", url))

    # Bookmarks bar
    bm_y = addr_y + 32
    cv2.rectangle(img, (wx + 4, bm_y), (wx + ww - 8, bm_y + 22), (242, 242, 242), -1)
    bm_items = ["Getting Started", "API Reference", "Examples", "FAQ"]
    bx = wx + 10
    for bm in bm_items:
        tw = cv2.getTextSize(bm, theme["font_face"], 0.4, 1)[0][0]
        cv2.putText(img, bm, (bx, bm_y + 15), theme["font_face"], 0.4, (0, 0, 200), 1)
        elems.append(UIElement(19, [bx, bm_y, tw, 22], "link", bm))
        bx += tw + 20

    # Content area
    content_y = bm_y + 28
    content_h = wh - (content_y - wy) - 8
    cv2.rectangle(img, (wx + 4, content_y), (wx + ww - 8, content_y + content_h), (255, 255, 255), -1)
    cv2.rectangle(img, (wx + 4, content_y), (wx + ww - 8, content_y + content_h), (200, 200, 200), 1)
    cv2.putText(img, "Welcome to WineBot", (wx + 20, content_y + 40),
                theme["font_face"], 0.8, (0, 0, 0), 2)
    cv2.putText(img, "Getting Started Guide", (wx + 20, content_y + 70),
                theme["font_face"], 0.5, (0, 100, 200), 1)
    elems.append(UIElement(19, [wx + 20, content_y + 52, 180, 22], "link", "Getting Started"))
    for k, line in enumerate(["Install the WineBot package:",
                                "  pip install winebot-cv",
                                "",
                                "Configure your first project:",
                                "  winebot init my-project",
                                "",
                                "Start the sidecar service:",
                                "  winebot serve --gpu"]):
        cv2.putText(img, line, (wx + 20, content_y + 110 + k * 20),
                    theme["font_face"], 0.4, (30, 30, 30), 1)

    # Scrollbar
    sb_x = wx + ww - 20
    cv2.rectangle(img, (sb_x, content_y), (sb_x + 16, content_y + content_h), (230, 230, 230), -1)
    cv2.rectangle(img, (sb_x, content_y + 10), (sb_x + 16, content_y + 80), (180, 180, 180), -1)
    cv2.rectangle(img, (sb_x, content_y + 10), (sb_x + 16, content_y + 80), (150, 150, 150), 1)
    elems.append(UIElement(13, [sb_x, content_y, 16, content_h], "scrollbar"))

    return GeneratedPage(image=img, elements=elems)


def make_terminal() -> GeneratedPage:
    """Terminal/console window with prompt, command output, scrollback."""
    theme = sample_theme()
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = draw_taskbar(img)
    wx, wy, ww, wh = 100, 60, 1080, 580
    # Dark terminal theme
    dark_theme = FRAMEWORK_THEMES["electron_dark"].copy()
    elems += draw_window(img, wx, wy, ww, wh, "Terminal", theme=dark_theme,
                         menu_items=["File", "Edit", "View", "Terminal", "Help"])

    term_y = wy + dark_theme["title_height"] + 22 + 4
    term_h = wh - (term_y - wy) - 8
    cv2.rectangle(img, (wx + 4, term_y), (wx + ww - 8, term_y + term_h), (20, 20, 28), -1)
    elems.append(UIElement(12, [wx + 4, term_y, ww - 8, term_h], "text_area"))

    # Terminal output with green prompt
    lines = [
        ("user@winebot:~$ ", "winebot --version"),
        ("", "WineBot CV/OCR Engine v2.0.0"),
        ("user@winebot:~$ ", "python3 train.py --epochs 30 --gpu"),
        ("", "Training complete: mAP50=0.871, mAP50-95=0.646"),
        ("", "Model saved: models/yolo/wine-finetuned-v2.pt (6.0MB)"),
        ("user@winebot:~$ ", "ls -la models/"),
        ("", "drwxr-xr-x  winebot  yolo/"),
        ("", "drwxr-xr-x  winebot  ocr/"),
        ("", "drwxr-xr-x  winebot  uidetr1/"),
        ("", "drwxr-xr-x  winebot  screenparser/"),
        ("user@winebot:~$ ", "_"),
    ]
    for k, (prompt, output) in enumerate(lines):
        ly = term_y + 14 + k * 20
        if prompt:
            cv2.putText(img, prompt, (wx + 12, ly),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 0), 1)
            cv2.putText(img, output, (wx + 12 + cv2.getTextSize(prompt, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[0][0], ly),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
        else:
            cv2.putText(img, output, (wx + 12, ly),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

    # Scrollbar
    sb_x = wx + ww - 20
    cv2.rectangle(img, (sb_x, term_y), (sb_x + 16, term_y + term_h), (40, 40, 48), -1)
    cv2.rectangle(img, (sb_x + 2, term_y + 30), (sb_x + 14, term_y + 100), (70, 70, 78), -1)
    cv2.rectangle(img, (sb_x + 2, term_y + 30), (sb_x + 14, term_y + 100), (100, 100, 108), 1)
    elems.append(UIElement(13, [sb_x, term_y, 16, term_h], "scrollbar"))

    return GeneratedPage(image=img, elements=elems)


def make_context_menu() -> GeneratedPage:
    """Right-click context menu popup over a desktop or application."""
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = draw_taskbar(img)

    # A window in the background for context
    wx, wy, ww, wh = 100, 60, 500, 400
    bg_theme = sample_theme()
    elems += draw_window(img, wx, wy, ww, wh, "Documents", theme=bg_theme,
                         menu_items=["File", "Edit", "View"])

    # Context menu popup (appears at cursor position)
    cm_x, cm_y = 300, 220
    cm_w, cm_h = 200, 0
    items = ["Open", "Edit", "Copy", "Paste", "", "Delete", "Rename", "", "Properties"]
    row_h = 24
    cm_h = len(items) * row_h

    # Menu background
    cv2.rectangle(img, (cm_x, cm_y), (cm_x + cm_w, cm_y + cm_h), (252, 252, 252), -1)
    cv2.rectangle(img, (cm_x, cm_y), (cm_x + cm_w, cm_y + cm_h), (160, 160, 160), 1)

    for k, item in enumerate(items):
        iy = cm_y + k * row_h
        if not item:
            cv2.line(img, (cm_x + 24, iy + row_h // 2),
                     (cm_x + cm_w - 6, iy + row_h // 2), (200, 200, 200), 1)
            continue
        if k == 0:
            cv2.rectangle(img, (cm_x + 2, iy), (cm_x + cm_w - 2, iy + row_h), (0, 120, 215), -1)
            cv2.putText(img, item, (cm_x + 28, iy + 17),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        else:
            cv2.putText(img, item, (cm_x + 28, iy + 17),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (30, 30, 30), 1)
        if item:
            elems.append(UIElement(9, [cm_x + 2, iy, cm_w - 4, row_h], "menu_item", item))

    # Subtle shadow behind menu
    overlay = img[cm_y + cm_h:cm_y + cm_h + 3, cm_x + 3:cm_x + cm_w + 3].copy()
    overlay = cv2.convertScaleAbs(overlay, alpha=0.85, beta=0)
    img[cm_y + cm_h:cm_y + cm_h + 3, cm_x + 3:cm_x + cm_w + 3] = overlay

    return GeneratedPage(image=img, elements=elems)


def make_wizard() -> GeneratedPage:
    """Multi-step installation/setup wizard with Back/Next/Finish buttons."""
    theme = sample_theme()
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = draw_taskbar(img)
    wx, wy, ww, wh = 180, 60, 920, 580
    elems += draw_window(img, wx, wy, ww, wh, "Setup Wizard", theme=theme, has_menu=False)

    content_top = wy + theme["title_height"] + 16

    # Steps indicator
    steps = ["Welcome", "License", "Directory", "Install", "Finish"]
    step_w = (ww - 40) // len(steps)
    for k, step in enumerate(steps):
        sx = wx + 20 + k * step_w
        color = (0, 120, 215) if k <= random.randint(1, 3) else (180, 180, 180)
        cv2.circle(img, (sx + step_w // 2, content_top + 12), 12, color, 2)
        cv2.putText(img, str(k + 1), (sx + step_w // 2 - 4, content_top + 17),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
        tw = cv2.getTextSize(step, cv2.FONT_HERSHEY_SIMPLEX, 0.35, 1)[0][0]
        cv2.putText(img, step, (sx + (step_w - tw) // 2, content_top + 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)
        elems.append(UIElement(15, [sx, content_top, step_w, 46], "tab", step))

    # Connector lines between steps
    for k in range(len(steps) - 1):
        sx1 = wx + 20 + k * step_w + step_w // 2 + 14
        sx2 = wx + 20 + (k + 1) * step_w + step_w // 2 - 14
        cv2.line(img, (sx1, content_top + 12), (sx2, content_top + 12),
                 (180, 180, 180), 2)

    # Step content area
    step_y = content_top + 60
    step_h = wh - (step_y - wy) - 60
    cv2.rectangle(img, (wx + 16, step_y), (wx + ww - 16, step_y + step_h), (255, 255, 255), -1)
    cv2.rectangle(img, (wx + 16, step_y), (wx + ww - 16, step_y + step_h), (200, 200, 200), 1)

    # Current step content (varies)
    current_step = random.randint(1, 4)
    if current_step <= 2:
        cv2.putText(img, "License Agreement", (wx + 36, step_y + 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
        license_box = (wx + 36, step_y + 44, ww - 72, step_h - 80)
        cv2.rectangle(img, (license_box[0], license_box[1]),
                      (license_box[0] + license_box[2], license_box[1] + license_box[3]),
                      (248, 248, 248), -1)
        cv2.rectangle(img, (license_box[0], license_box[1]),
                      (license_box[0] + license_box[2], license_box[1] + license_box[3]),
                      (190, 190, 190), 1)
        for kl, lc_line in enumerate(["END USER LICENSE AGREEMENT",
                                        "",
                                        "This software is provided as-is.",
                                        "You may freely use, copy, and distribute",
                                        "this software subject to the license terms.",
                                        "",
                                        "Copyright (C) 2026 WineBot Project"]):
            cv2.putText(img, lc_line, (license_box[0] + 10, license_box[1] + 22 + kl * 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (30, 30, 30), 1)
        # Radio: accept
        rb_y = license_box[1] + license_box[3] + 14
        cv2.circle(img, (wx + 56, rb_y + 8), 8, (100, 100, 100), 1)
        if random.random() > 0.3:
            cv2.circle(img, (wx + 56, rb_y + 8), 4, (0, 150, 0), -1)
        cv2.putText(img, "I accept the agreement", (wx + 74, rb_y + 13),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
        elems.append(UIElement(7, [wx + 36, rb_y, 200, 24], "radio", "accept"))
    elif current_step == 3:
        cv2.putText(img, "Installation Directory", (wx + 36, step_y + 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
        tf_y = step_y + 64
        cv2.rectangle(img, (wx + 36, tf_y), (wx + ww - 100, tf_y + 30), (255, 255, 255), -1)
        cv2.rectangle(img, (wx + 36, tf_y), (wx + ww - 100, tf_y + 30), (150, 150, 150), 1)
        path = "C:\\Program Files\\WineBot"
        cv2.putText(img, path, (wx + 44, tf_y + 21),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
        elems.append(UIElement(4, [wx + 36, tf_y, ww - 136, 30], "text_field", path))
        elems.append(draw_button(img, wx + ww - 56, tf_y, 48, 30, "...", theme))
        # Disk space
        cv2.putText(img, "Required space: 250 MB", (wx + 36, tf_y + 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (80, 80, 80), 1)
        cv2.putText(img, f"Available space: {random.randint(50,500)} GB",
                    (wx + 36, tf_y + 70), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (80, 80, 80), 1)
    elif current_step == 4:
        cv2.putText(img, "Ready to Install", (wx + 36, step_y + 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1)
        cv2.putText(img, "The wizard is ready to begin installation.", (wx + 36, step_y + 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (50, 50, 50), 1)
        # Progress bar
        pb_y = step_y + 120
        pb_w_c = ww - 80
        pb_h = 26
        cv2.rectangle(img, (wx + 36, pb_y), (wx + 36 + pb_w_c, pb_y + pb_h), (230, 230, 230), -1)
        cv2.rectangle(img, (wx + 36, pb_y), (wx + 36 + pb_w_c, pb_y + pb_h), (150, 150, 150), 1)
        fill = int(pb_w_c * random.uniform(0.3, 0.9))
        cv2.rectangle(img, (wx + 36, pb_y), (wx + 36 + fill, pb_y + pb_h),
                      (0, 160, 0), -1)
        pct = int(fill / pb_w_c * 100)
        cv2.putText(img, f"{pct}%", (wx + 36 + pb_w_c // 2 - 15, pb_y + 19),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
        elems.append(UIElement(16, [wx + 36, pb_y, pb_w_c, pb_h], "progress_bar"))

    # Navigation buttons
    btn_y = wy + wh - 46
    if current_step > 1:
        elems.append(draw_button(img, wx + ww - 220, btn_y, 80, 30, "< Back", theme))
    if current_step < 4:
        elems.append(draw_button(img, wx + ww - 120, btn_y, 80, 30, "Next >", theme, primary=True))
    else:
        elems.append(draw_button(img, wx + ww - 120, btn_y, 80, 30, "Finish", theme, primary=True))
    if current_step < 4:
        elems.append(draw_button(img, wx + ww - 320, btn_y, 80, 30, "Cancel", theme))

    return GeneratedPage(image=img, elements=elems)


# ── Workflow scenes ─────────────────────────────────────────────────────

def make_find_replace() -> GeneratedPage:
    """Find/Replace dialog — common in text editors, IDEs, word processors."""
    theme = sample_theme()
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = draw_taskbar(img)

    dlg_w, dlg_h = 420, 200
    dlg_x, dlg_y = (DESKTOP_SIZE[0] - dlg_w) // 2, 120
    cv2.rectangle(img, (dlg_x, dlg_y), (dlg_x + dlg_w, dlg_y + dlg_h), (255, 255, 255), -1)
    cv2.rectangle(img, (dlg_x, dlg_y), (dlg_x + dlg_w, dlg_y + dlg_h), (150, 150, 150), 2)
    cv2.rectangle(img, (dlg_x, dlg_y), (dlg_x + dlg_w, dlg_y + theme["title_height"]),
                  theme["title_color"], -1)
    cv2.putText(img, "Find and Replace", (dlg_x + 10, dlg_y + theme["title_height"] - 7),
                theme["font_face"], theme["title_font_scale"], theme["title_text_color"], 1)
    elems.append(UIElement(0, [dlg_x, dlg_y, dlg_w, theme["title_height"]], "title_bar"))
    elems.append(UIElement(1, [dlg_x + 10, dlg_y + 3, 120, theme["title_height"] - 6],
                           "title_text", "Find and Replace"))

    content_y = dlg_y + theme["title_height"] + 10
    labels = ["Find what:", "Replace with:"]
    for k, label in enumerate(labels):
        ly = content_y + k * 34
        cv2.putText(img, label, (dlg_x + 12, ly + 16), theme["font_face"], 0.45, (50, 50, 50), 1)
        tf_x = dlg_x + 110
        tf_w = dlg_w - 130
        tf_h = 26
        cv2.rectangle(img, (tf_x, ly), (tf_x + tf_w, ly + tf_h), (255, 255, 255), -1)
        cv2.rectangle(img, (tf_x, ly), (tf_x + tf_w, ly + tf_h), (150, 150, 150), 1)
        text = "winebot" if k == 0 else "WineBot"
        cv2.putText(img, text, (tf_x + 6, ly + 18), theme["font_face"], 0.45, (0, 0, 0), 1)
        elems.append(UIElement(4, [tf_x, ly, tf_w, tf_h], "text_field", text))

    # Checkboxes
    cb_y = content_y + 80
    for j, cb_label in enumerate(["Match case", "Match whole word only", "Wrap around"]):
        bx = dlg_x + 12 + j * 140
        cv2.rectangle(img, (bx, cb_y), (bx + 16, cb_y + 16), (255, 255, 255), -1)
        cv2.rectangle(img, (bx, cb_y), (bx + 16, cb_y + 16), (100, 100, 100), 1)
        if j == 0 or j == 2:
            cv2.line(img, (bx + 3, cb_y + 8), (bx + 8, cb_y + 12), (0, 150, 0), 2)
            cv2.line(img, (bx + 8, cb_y + 12), (bx + 14, cb_y + 3), (0, 150, 0), 2)
        cv2.putText(img, cb_label, (bx + 22, cb_y + 13), theme["font_face"], 0.35, (30, 30, 30), 1)
        elems.append(UIElement(6, [bx, cb_y, 16, 16], "checkbox", cb_label))

    # Buttons
    btn_y = dlg_y + dlg_h - 40
    for bx, label, primary in [
        (dlg_x + dlg_w - 240, "Find Next", True),
        (dlg_x + dlg_w - 160, "Replace", False),
        (dlg_x + dlg_w - 80, "Replace All", False),
    ]:
        elems.append(draw_button(img, bx, btn_y, 72, 28, label, theme, primary=primary))

    return GeneratedPage(image=img, elements=elems)


def make_print_dialog() -> GeneratedPage:
    """Print dialog — printer selection, page range, copies."""
    theme = sample_theme()
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = draw_taskbar(img)

    dlg_w, dlg_h = 480, 340
    dlg_x, dlg_y = (DESKTOP_SIZE[0] - dlg_w) // 2, 80
    cv2.rectangle(img, (dlg_x, dlg_y), (dlg_x + dlg_w, dlg_y + dlg_h), (255, 255, 255), -1)
    cv2.rectangle(img, (dlg_x, dlg_y), (dlg_x + dlg_w, dlg_y + dlg_h), (150, 150, 150), 2)
    cv2.rectangle(img, (dlg_x, dlg_y), (dlg_x + dlg_w, dlg_y + theme["title_height"]),
                  theme["title_color"], -1)
    cv2.putText(img, "Print", (dlg_x + 10, dlg_y + theme["title_height"] - 7),
                theme["font_face"], theme["title_font_scale"], theme["title_text_color"], 1)
    elems.append(UIElement(0, [dlg_x, dlg_y, dlg_w, theme["title_height"]], "title_bar"))

    content_y = dlg_y + theme["title_height"] + 10
    # Printer group
    cv2.putText(img, "Printer", (dlg_x + 12, content_y + 16), theme["font_face"], 0.5, (0, 0, 0), 1)
    printers = ["HP LaserJet P3015 (network)", "PDF Writer", "Microsoft Print to PDF"]
    dd_x, dd_y = dlg_x + 100, content_y
    dd_w, dd_h = dlg_w - 120, 26
    cv2.rectangle(img, (dd_x, dd_y), (dd_x + dd_w, dd_y + dd_h), (255, 255, 255), -1)
    cv2.rectangle(img, (dd_x, dd_y), (dd_x + dd_w, dd_y + dd_h), (150, 150, 150), 1)
    cv2.putText(img, random.choice(printers), (dd_x + 6, dd_y + 18),
                theme["font_face"], 0.45, (0, 0, 0), 1)
    elems.append(UIElement(5, [dd_x, dd_y, dd_w, dd_h], "dropdown", printers[0]))

    # Print range
    range_y = content_y + 40
    cv2.rectangle(img, (dlg_x + 10, range_y), (dlg_x + dlg_w - 20, range_y + 70), (248, 248, 248), -1)
    cv2.putText(img, "Print range", (dlg_x + 18, range_y + 20), theme["font_face"], 0.45, (50, 50, 50), 1)
    options = ["All", "Selection", "Pages:", "Current page"]
    for j, opt in enumerate(options):
        rx = dlg_x + 24 + j * 110
        cv2.circle(img, (rx + 8, range_y + 42), 8, (100, 100, 100), 1)
        if j == 0:
            cv2.circle(img, (rx + 8, range_y + 42), 4, (0, 120, 215), -1)
        cv2.putText(img, opt, (rx + 20, range_y + 47), theme["font_face"], 0.35, (30, 30, 30), 1)
        elems.append(UIElement(7, [rx, range_y + 30, 70, 24], "radio", opt))
    # Pages input if "Pages:" selected
    pg_x = dlg_x + 24 + 3 * 110 + 30
    cv2.rectangle(img, (pg_x, range_y + 32), (pg_x + 60, range_y + 56), (255, 255, 255), -1)
    cv2.rectangle(img, (pg_x, range_y + 32), (pg_x + 60, range_y + 56), (150, 150, 150), 1)
    cv2.putText(img, "1-5", (pg_x + 4, range_y + 50), theme["font_face"], 0.4, (0, 0, 0), 1)
    elems.append(UIElement(4, [pg_x, range_y + 32, 60, 24], "text_field", "1-5"))

    # Copies
    cp_y = range_y + 80
    cv2.putText(img, "Copies:", (dlg_x + 12, cp_y + 16), theme["font_face"], 0.45, (50, 50, 50), 1)
    # Spinner
    sp_x = dlg_x + 80
    sp_w, sp_h = 60, 26
    cv2.rectangle(img, (sp_x, cp_y), (sp_x + sp_w, cp_y + sp_h), (255, 255, 255), -1)
    cv2.rectangle(img, (sp_x, cp_y), (sp_x + sp_w, cp_y + sp_h), (150, 150, 150), 1)
    cv2.putText(img, "1", (sp_x + 4, cp_y + 18), theme["font_face"], 0.45, (0, 0, 0), 1)
    # Up/down arrows
    cv2.rectangle(img, (sp_x + sp_w - 18, cp_y + 2), (sp_x + sp_w - 2, cp_y + 12), (220, 220, 220), -1)
    cv2.rectangle(img, (sp_x + sp_w - 18, cp_y + 14), (sp_x + sp_w - 2, cp_y + 24), (220, 220, 220), -1)
    cv2.putText(img, "^", (sp_x + sp_w - 16, cp_y + 10), theme["font_face"], 0.3, (50, 50, 50), 1)
    cv2.putText(img, "v", (sp_x + sp_w - 16, cp_y + 22), theme["font_face"], 0.3, (50, 50, 50), 1)
    elems.append(UIElement(21, [sp_x, cp_y, sp_w, sp_h], "spinner_button", "1"))

    # Collate checkbox
    cb_x = dlg_x + 180
    cv2.rectangle(img, (cb_x, cp_y), (cb_x + 16, cp_y + 16), (255, 255, 255), -1)
    cv2.rectangle(img, (cb_x, cp_y), (cb_x + 16, cp_y + 16), (100, 100, 100), 1)
    cv2.line(img, (cb_x + 3, cp_y + 8), (cb_x + 8, cp_y + 12), (0, 150, 0), 2)
    cv2.line(img, (cb_x + 8, cp_y + 12), (cb_x + 14, cp_y + 3), (0, 150, 0), 2)
    cv2.putText(img, "Collate", (cb_x + 22, cp_y + 13), theme["font_face"], 0.4, (30, 30, 30), 1)
    elems.append(UIElement(6, [cb_x, cp_y, 16, 16], "checkbox", "Collate"))

    # Buttons
    btn_y = dlg_y + dlg_h - 40
    elems.append(draw_button(img, dlg_x + dlg_w - 180, btn_y, 80, 28, "Cancel", theme))
    elems.append(draw_button(img, dlg_x + dlg_w - 90, btn_y, 70, 28, "Print", theme, primary=True))

    return GeneratedPage(image=img, elements=elems)


def make_about_dialog() -> GeneratedPage:
    """About/Help → About dialog with version, copyright, credits."""
    theme = sample_theme()
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = draw_taskbar(img)

    dlg_w, dlg_h = 380, 240
    dlg_x, dlg_y = (DESKTOP_SIZE[0] - dlg_w) // 2, 120
    cv2.rectangle(img, (dlg_x, dlg_y), (dlg_x + dlg_w, dlg_y + dlg_h), (255, 255, 255), -1)
    cv2.rectangle(img, (dlg_x, dlg_y), (dlg_x + dlg_w, dlg_y + dlg_h), (150, 150, 150), 2)
    cv2.rectangle(img, (dlg_x, dlg_y), (dlg_x + dlg_w, dlg_y + theme["title_height"]),
                  theme["title_color"], -1)
    title = f"About {random.choice(['WineBot', 'Notepad', '7-Zip', 'VLC Media Player'])}"
    cv2.putText(img, title, (dlg_x + 10, dlg_y + theme["title_height"] - 7),
                theme["font_face"], theme["title_font_scale"], theme["title_text_color"], 1)
    elems.append(UIElement(0, [dlg_x, dlg_y, dlg_w, theme["title_height"]], "title_bar"))

    content_y = dlg_y + theme["title_height"] + 8
    # Icon
    cv2.rectangle(img, (dlg_x + 20, content_y + 20), (dlg_x + 80, content_y + 80),
                  (0, 120, 215), -1)
    cv2.putText(img, "WB", (dlg_x + 30, content_y + 60),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    elems.append(UIElement(20, [dlg_x + 20, content_y + 20, 60, 60], "icon"))

    lines = ["WineBot CV/OCR Engine",
             "Version 2.0.0",
             "",
             "Copyright (C) 2026 WineBot Project",
             "Licensed under AGPL-3.0",
             "",
             "Build: winebot-cv:gpu",
             "Commit: 6981d2b"]
    for k, line in enumerate(lines):
        ly = content_y + 20 + k * 20
        color = (0, 0, 0) if k < 2 else (80, 80, 80)
        cv2.putText(img, line, (dlg_x + 100, ly), theme["font_face"], 0.4, color, 1)

    elems.append(draw_button(img, dlg_x + dlg_w - 90, dlg_y + dlg_h - 40, 70, 28,
                             "OK", theme, primary=True))

    return GeneratedPage(image=img, elements=elems)


def make_file_properties() -> GeneratedPage:
    """File/folder Properties dialog — General, Security, Details tabs."""
    theme = sample_theme()
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = draw_taskbar(img)

    dlg_w, dlg_h = 400, 380
    dlg_x, dlg_y = (DESKTOP_SIZE[0] - dlg_w) // 2, 80
    cv2.rectangle(img, (dlg_x, dlg_y), (dlg_x + dlg_w, dlg_y + dlg_h), (255, 255, 255), -1)
    cv2.rectangle(img, (dlg_x, dlg_y), (dlg_x + dlg_w, dlg_y + dlg_h), (150, 150, 150), 2)
    cv2.rectangle(img, (dlg_x, dlg_y), (dlg_x + dlg_w, dlg_y + theme["title_height"]),
                  theme["title_color"], -1)
    cv2.putText(img, "document.txt Properties", (dlg_x + 10, dlg_y + theme["title_height"] - 7),
                theme["font_face"], theme["title_font_scale"], theme["title_text_color"], 1)
    elems.append(UIElement(0, [dlg_x, dlg_y, dlg_w, theme["title_height"]], "title_bar"))

    # Tabs
    tab_y = dlg_y + theme["title_height"]
    tabs = ["General", "Security", "Details", "Previous Versions"]
    tx = dlg_x + 4
    for tab in tabs:
        tw = cv2.getTextSize(tab, theme["font_face"], 0.4, 1)[0][0]
        cv2.rectangle(img, (tx, tab_y + 2), (tx + tw + 12, tab_y + 24), (240, 240, 240), -1)
        cv2.rectangle(img, (tx, tab_y + 2), (tx + tw + 12, tab_y + 24), (180, 180, 180), 1)
        cv2.putText(img, tab, (tx + 6, tab_y + 18), theme["font_face"], 0.4, (30, 30, 30), 1)
        elems.append(UIElement(15, [tx, tab_y + 2, tw + 12, 22], "tab", tab))
        tx += tw + 16

    content_y = tab_y + 32
    # File icon + name
    cv2.rectangle(img, (dlg_x + 20, content_y), (dlg_x + 68, content_y + 48), (0, 120, 215), -1)
    cv2.putText(img, "TXT", (dlg_x + 28, content_y + 33),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    elems.append(UIElement(20, [dlg_x + 20, content_y, 48, 48], "icon"))
    cv2.putText(img, "document.txt", (dlg_x + 80, content_y + 28),
                theme["font_face"], 0.5, (0, 0, 0), 1)

    # Property rows
    fields = [
        ("Type of file:", "Text Document (.txt)"),
        ("Opens with:", "Notepad"),
        ("Location:", "C:\\Users\\winebot\\Documents"),
        ("Size:", f"{random.randint(1,500):,} bytes"),
        ("Size on disk:", f"{random.randint(4,504):,} bytes"),
        ("Created:", "June 23, 2026 10:15 AM"),
        ("Modified:", "June 23, 2026 2:30 PM"),
        ("Accessed:", "June 23, 2026 2:30 PM"),
    ]
    for k, (label, value) in enumerate(fields):
        fy = content_y + 60 + k * 28
        cv2.putText(img, label, (dlg_x + 20, fy + 15), theme["font_face"], 0.4, (60, 60, 60), 1)
        cv2.putText(img, value, (dlg_x + 140, fy + 15), theme["font_face"], 0.4, (0, 0, 0), 1)

    # Attributes checkboxes
    attr_y = content_y + 60 + len(fields) * 28 + 10
    for j, attr in enumerate(["Read-only", "Hidden"]):
        ax = dlg_x + 20 + j * 120
        cv2.rectangle(img, (ax, attr_y), (ax + 16, attr_y + 16), (255, 255, 255), -1)
        cv2.rectangle(img, (ax, attr_y), (ax + 16, attr_y + 16), (100, 100, 100), 1)
        cv2.putText(img, attr, (ax + 22, attr_y + 13), theme["font_face"], 0.4, (30, 30, 30), 1)
        elems.append(UIElement(6, [ax, attr_y, 16, 16], "checkbox", attr))

    # Buttons
    btn_y = dlg_y + dlg_h - 40
    elems.append(draw_button(img, dlg_x + dlg_w - 180, btn_y, 80, 28, "Cancel", theme))
    elems.append(draw_button(img, dlg_x + dlg_w - 90, btn_y, 70, 28, "OK", theme, primary=True))

    return GeneratedPage(image=img, elements=elems)


def make_system_tray_popup() -> GeneratedPage:
    """System tray notification/popup above the taskbar clock."""
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = draw_taskbar(img)

    # A background window for context
    wx, wy, ww, wh = 200, 80, 600, 400
    bg_theme = sample_theme()
    elems += draw_window(img, wx, wy, ww, wh, "Application", theme=bg_theme,
                         menu_items=["File", "Edit", "Help"])

    # System tray popup (rises from taskbar, right-aligned)
    popup_w, popup_h = 320, 200
    px = DESKTOP_SIZE[0] - popup_w - 10
    py = DESKTOP_SIZE[1] - TASKBAR_HEIGHT - popup_h - 4
    cv2.rectangle(img, (px, py), (px + popup_w, py + popup_h), (255, 255, 255), -1)
    cv2.rectangle(img, (px, py), (px + popup_w, py + popup_h), (150, 150, 150), 1)

    # Title bar
    popup_theme = sample_theme()
    cv2.rectangle(img, (px, py), (px + popup_w, py + popup_theme["title_height"]),
                  popup_theme["title_color"], -1)
    notif_title = random.choice(["WineBot Update", "Backup Complete",
                                  "Scan Finished", "New Message"])
    cv2.putText(img, notif_title, (px + 8, py + popup_theme["title_height"] - 7),
                popup_theme["font_face"], popup_theme["title_font_scale"], (255, 255, 255), 1)
    elems.append(UIElement(0, [px, py, popup_w, popup_theme["title_height"]], "title_bar"))

    # Content
    cv2.putText(img, notif_title, (px + 12, py + popup_theme["title_height"] + 24),
                popup_theme["font_face"], 0.5, (0, 0, 0), 1)
    body = random.choice([
        "A new version of WineBot is available.\nClick to download and install.",
        "Your backup completed successfully.\nAll files were saved.",
        "Threat scan complete. No threats detected.\nLast scan: 2 minutes ago.",
    ])
    for k, body_line in enumerate(body.split("\n")):
        cv2.putText(img, body_line, (px + 12, py + popup_theme["title_height"] + 48 + k * 20),
                    popup_theme["font_face"], 0.38, (60, 60, 60), 1)

    # Action buttons/links
    link_y = py + popup_h - 30
    cv2.putText(img, "Open WineBot", (px + 12, link_y + 12),
                popup_theme["font_face"], 0.4, (0, 100, 200), 1)
    elems.append(UIElement(19, [px + 12, link_y, 90, 20], "link", "Open WineBot"))
    cv2.putText(img, "Dismiss", (px + popup_w - 60, link_y + 12),
                popup_theme["font_face"], 0.4, (120, 120, 120), 1)
    elems.append(UIElement(19, [px + popup_w - 60, link_y, 50, 20], "link", "Dismiss"))

    return GeneratedPage(image=img, elements=elems)


# ── Generator registry ──────────────────────────────────────────────────

def make_form_fill() -> GeneratedPage:
    """Dense government/customs form with labeled fields, checkboxes, signature block.

    Simulates PS Form 2976, I-9, W-4, or similar structured forms that combine
    text fields, checkboxes, radio groups, date pickers, and signature areas
    in a dense single-page layout — common in PDF/acrobat workflows.
    """
    theme = sample_theme()
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = draw_taskbar(img)
    wx, wy, ww, wh = 80, 40, 1120, 640
    elems += draw_window(img, wx, wy, ww, wh,
                         random.choice(["PS Form 2976 — Customs Declaration",
                                        "Form I-9 — Employment Eligibility",
                                        "Form W-4 — Employee's Withholding"]),
                         theme=theme, has_menu=False)

    content_y = wy + theme["title_height"] + 8

    # ── Section headers with horizontal rules ──
    sections = [
        ("Sender Information", ["Full Name:", "Street Address:", "City/State/ZIP:",
                                 "CMR/PSC Box:", "APO/FPO/DPO:"]),
        ("Addressee Information", ["Full Name:", "Company:", "Street Address:",
                                    "City/State/ZIP:", "Country:"]),
        ("Item Description (USPS 2026 — detailed required)",
         ["Item 1:", "  Description:", "  HS Code:", "  Value ($):", "  Weight (lbs):",
          "Item 2:", "  Description:", "  HS Code:", "  Value ($):", "  Weight (lbs):"]),
        ("Declaration", ["Category:", "  [ ] Gift  [ ] Commercial Sample  [ ] Documents",
                         "  [x] Returned Goods  [ ] Other",
                         "Signature:", "Date:"]),
    ]

    section_y = content_y
    for section_title, fields in sections:
        # Section header
        cv2.rectangle(img, (wx + 8, section_y), (wx + ww - 8, section_y + 22),
                      (230, 230, 240), -1)
        cv2.putText(img, section_title, (wx + 12, section_y + 16),
                    theme["font_face"], 0.5, (0, 0, 0), 1)
        section_y += 28

        for field in fields:
            if field.strip().startswith("["):
                # Checkbox/radio line
                cv2.putText(img, field, (wx + 16, section_y + 14),
                            theme["font_face"], 0.4, (30, 30, 30), 1)
                if "x" in field.split("]")[0]:
                    cv2.rectangle(img, (wx + 20, section_y), (wx + 34, section_y + 16),
                                  (255, 255, 255), -1)
                    cv2.rectangle(img, (wx + 20, section_y), (wx + 34, section_y + 16),
                                  (100, 100, 100), 1)
                    # Draw checkmark
                    cv2.line(img, (wx + 23, section_y + 8), (wx + 27, section_y + 12),
                             (0, 140, 0), 2)
                    cv2.line(img, (wx + 27, section_y + 12), (wx + 32, section_y + 3),
                             (0, 140, 0), 2)
                section_y += 20
            elif field == "Signature:":
                cv2.putText(img, field, (wx + 16, section_y + 14),
                            theme["font_face"], 0.4, (30, 30, 30), 1)
                # Signature line
                sig_x = wx + 100
                cv2.line(img, (sig_x, section_y + 16), (sig_x + 200, section_y + 16),
                         (180, 180, 180), 1)
                elems.append(UIElement(4, [sig_x, section_y, 200, 20], "text_field", "signature"))
                section_y += 24
            elif field == "Date:":
                cv2.putText(img, field, (wx + 16, section_y + 14),
                            theme["font_face"], 0.4, (30, 30, 30), 1)
                dt = f"{random.randint(1,12):02d}/{random.randint(1,28):02d}/{random.randint(2022,2026)}"
                cv2.putText(img, dt, (wx + 100, section_y + 14),
                            theme["font_face"], 0.4, (0, 0, 0), 1)
                elems.append(UIElement(4, [wx + 100, section_y, 80, 20], "text_field", dt))
                section_y += 24
            elif field.startswith("  "):
                # Indented sub-field
                cv2.putText(img, field.strip(), (wx + 32, section_y + 14),
                            theme["font_face"], 0.38, (50, 50, 50), 1)
                # Small text field for value
                tf_x = wx + 180
                tf_w = 180 if "Description" in field else 80
                if "HS Code" in field or "Value" in field or "Weight" in field:
                    cv2.rectangle(img, (tf_x, section_y), (tf_x + tf_w, section_y + 18),
                                  (255, 255, 255), -1)
                    cv2.rectangle(img, (tf_x, section_y), (tf_x + tf_w, section_y + 18),
                                  (180, 180, 180), 1)
                    val = random.choice(["8471.30", "29.99", "0.75", "8544.42", "20.00", "0.5"])
                    cv2.putText(img, val, (tf_x + 4, section_y + 13),
                                theme["font_face"], 0.35, (0, 0, 0), 1)
                    elems.append(UIElement(4, [tf_x, section_y, tf_w, 18], "text_field", val))
                section_y += 20
            else:
                # Label + text field
                cv2.putText(img, field, (wx + 16, section_y + 14),
                            theme["font_face"], 0.4, (30, 30, 30), 1)
                tf_x = wx + 180
                tf_w = ww - 220
                tf_h = 18
                cv2.rectangle(img, (tf_x, section_y), (tf_x + tf_w, section_y + tf_h),
                              (255, 255, 255), -1)
                cv2.rectangle(img, (tf_x, section_y), (tf_x + tf_w, section_y + tf_h),
                              (180, 180, 180), 1)
                # Pre-fill some fields
                fill_map = {
                    "Full Name:": "SGT Michael Rodriguez",
                    "Company:": "Amazon Returns Center",
                    "Street Address:": "1850 Mercer Road",
                    "City/State/ZIP:": "Lexington, KY 40511",
                    "Country:": "United States",
                    "CMR/PSC Box:": "CMR 451 Box 1234",
                    "APO/FPO/DPO:": "APO AE 09128",
                }
                val = fill_map.get(field, field.replace(":", "").lower())
                cv2.putText(img, val, (tf_x + 4, section_y + 13),
                            theme["font_face"], 0.38, (0, 0, 0), 1)
                elems.append(UIElement(4, [tf_x, section_y, tf_w, tf_h], "text_field", val))
                section_y += 22

        section_y += 6  # Gap between sections

    # ── Action buttons at bottom ──
    btn_y = wy + wh - 40
    elems.append(draw_button(img, wx + ww - 300, btn_y, 90, 28, "Reset Form", theme))
    elems.append(draw_button(img, wx + ww - 200, btn_y, 90, 28, "Save Draft", theme))
    elems.append(draw_button(img, wx + ww - 100, btn_y, 90, 28, "Submit", theme, primary=True))

    # ── Status bar ──
    sb_y = wy + wh - 20
    cv2.rectangle(img, (wx, sb_y), (wx + ww, sb_y + 20), (240, 240, 240), -1)
    cv2.rectangle(img, (wx, sb_y), (wx + ww, sb_y + 20), WINDOW_BORDER, 1)
    cv2.putText(img, "Form PS 2976 | Page 1 of 1 | Fields: 18 completed / 22 total",
                (wx + 8, sb_y + 14), theme["font_face"], 0.35, (80, 80, 80), 1)
    elems.append(UIElement(18, [wx, sb_y, ww, 20], "status_bar"))

    return GeneratedPage(image=img, elements=elems)


def make_file_manager() -> GeneratedPage:
    """File manager with tree sidebar, file list, toolbar, path bar."""
    theme = sample_theme()
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = []

    elems += draw_taskbar(img)
    wx, wy, ww, wh = 100, 50, 1080, 620
    elems += draw_window(img, wx, wy, ww, wh, "File Explorer", theme=theme,
                         menu_items=["File", "Edit", "View", "Tools", "Help"])

    # Toolbar with back/forward/up/path
    tb_y = wy + theme["title_height"] + 22 + 2
    cv2.rectangle(img, (wx, tb_y), (wx + ww, tb_y + 28), (238, 238, 238), -1)
    for i, tool in enumerate(["Back", "Forward", "Up", "Refresh", "New Folder"]):
        bx = wx + 6 + i * 74
        elems.append(draw_button(img, bx, tb_y + 2, 68, 24, tool, theme))
    elems.append(UIElement(17, [wx, tb_y, ww, 28], "toolbar"))

    # Path bar
    path_y = tb_y + 34
    cv2.rectangle(img, (wx, path_y), (wx + ww, path_y + 22), (255, 255, 255), -1)
    cv2.rectangle(img, (wx, path_y), (wx + ww, path_y + 22), (180, 180, 180), 1)
    path_text = "C:\\Users\\winebot\\Documents\\"
    cv2.putText(img, path_text, (wx + 8, path_y + 16),
                theme["font_face"], 0.4, (30, 30, 30), 1)
    elems.append(UIElement(4, [wx, path_y, ww, 22], "text_field", path_text))

    # Tree sidebar
    tree_y = path_y + 28
    tree_w = 200
    tree_h = wh - (tree_y - wy) - 24
    cv2.rectangle(img, (wx, tree_y), (wx + tree_w, tree_y + tree_h), (250, 250, 250), -1)
    cv2.rectangle(img, (wx, tree_y), (wx + tree_w, tree_y + tree_h), (190, 190, 190), 1)
    tree_items = ["Desktop", "  Documents", "    Projects", "    Reports",
                  "  Downloads", "  Music", "  Pictures", "  Videos",
                  "This PC", "  Local Disk (C:)", "  Network (Z:)"]
    for i, item in enumerate(tree_items):
        ty = tree_y + 6 + i * 22
        indent = item.count("  ") * 14
        cv2.putText(img, item.strip(), (wx + 4 + indent, ty + 15),
                    theme["font_face"], 0.4, (30, 30, 30), 1)
        if item.strip():
            tw = cv2.getTextSize(item.strip(), theme["font_face"], 0.4, 1)[0][0]
            elems.append(UIElement(14, [wx + 4 + indent, ty, tw + 4, 22], "list_item", item.strip()))

    # File list
    fl_y = tree_y
    fl_x = wx + tree_w + 4
    fl_w = ww - tree_w - 8
    fl_h = tree_h
    cv2.rectangle(img, (fl_x, fl_y), (fl_x + fl_w, fl_y + fl_h), (255, 255, 255), -1)
    cv2.rectangle(img, (fl_x, fl_y), (fl_x + fl_w, fl_y + fl_h), (190, 190, 190), 1)
    files = ["document.txt", "report_v2.pdf", "screenshot.png",
             "data_export.csv", "archive.zip", "README.md",
             "config.json", "notes.md", "image_001.jpg", "video.mp4"]
    for i, fname in enumerate(files):
        fy = fl_y + 6 + i * 24
        cv2.putText(img, fname, (fl_x + 8, fy + 17),
                    theme["font_face"], 0.4, (0, 0, 30), 1)
        elems.append(UIElement(14, [fl_x + 8, fy, fl_w - 16, 24], "list_item", fname))

    return GeneratedPage(image=img, elements=elems)


def make_multi_window() -> GeneratedPage:
    """2-4 overlapping windows from different frameworks simultaneously."""
    img = np.ones((DESKTOP_SIZE[1], DESKTOP_SIZE[0], 3), dtype=np.uint8)
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = draw_taskbar(img)

    # Place 2-3 overlapping windows from different frameworks
    windows = [
        (40, 30, 600, 380, "Document - Editor", ["File", "Edit", "View"], "win32_classic"),
        (180, 120, 550, 420, "Settings", ["General", "Network"], "gtk_adwaita"),
        (320, 60, 500, 350, "About", None, "java_metal"),
    ]
    for _i, (x, y, w, h, title, menus, fw) in enumerate(windows[:random.randint(2, 3)]):
        theme = FRAMEWORK_THEMES[fw].copy()
        theme["title_height"] += random.randint(-2, 2)
        elems += draw_window(img, x, y, w, h, title, theme=theme,
                             has_menu=menus is not None, menu_items=menus)

        # Add some content in each window
        if "Document" in title:
            for j, line in enumerate(["Hello World", "This is a test.", "Line three."]):
                ly = y + theme["title_height"] + 28 + j * 20
                cv2.putText(img, line, (x + 8, ly),
                            theme["font_face"], 0.4, (0, 0, 0), 1)
        elif "Settings" in title:
            cb_y = y + theme["title_height"] + 40
            for j, cb in enumerate(["Enable feature A", "Show hidden files"]):
                by = cb_y + j * 28
                cv2.rectangle(img, (x + 16, by), (x + 32, by + 16), (255, 255, 255), -1)
                cv2.rectangle(img, (x + 16, by), (x + 32, by + 16), (100, 100, 100), 2)
                if j == 0:
                    cv2.line(img, (x + 19, by + 8), (x + 24, by + 12), (0, 140, 0), 2)
                    cv2.line(img, (x + 24, by + 12), (x + 30, by + 3), (0, 140, 0), 2)
                cv2.putText(img, cb, (x + 40, by + 13),
                            theme["font_face"], 0.4, (30, 30, 30), 1)
                elems.append(UIElement(6, [x + 16, by, 16, 16], "checkbox", cb))
        elif "About" in title:
            about_y = y + theme["title_height"] + 30
            cv2.putText(img, "WineBot v1.0", (x + 100, about_y),
                        theme["font_face"], 0.7, (0, 0, 0), 1)
            cv2.putText(img, "Copyright 2026", (x + 80, about_y + 30),
                        theme["font_face"], 0.45, (80, 80, 80), 1)
            elems.append(draw_button(img, x + w - 90, y + h - 40, 70, 26, "OK", theme, primary=True))

    return GeneratedPage(image=img, elements=elems)


# ── Additional Scene Types ────────────────────────────────────────────────
# Login screen, toast notifications, data tables, drag-and-drop, loading screens


def make_login_screen() -> GeneratedPage:
    """Login/authentication screen with username, password, and submit."""
    theme = sample_theme()
    dw, dh = DESKTOP_SIZE
    img = np.ones((dh, dw, 3), dtype=np.uint8) * 60
    overlay = img.copy()
    cv2.rectangle(overlay, (0, 0), (dw, dh), (70, 70, 90), -1)
    cv2.addWeighted(overlay, 0.3, img, 0.7, 0, img)
    pw, ph = 340, 320
    px, py = (dw - pw) // 2, (dh - ph) // 2 - 40
    cv2.rectangle(img, (px, py), (px + pw, py + ph), (240, 240, 245), -1)
    cv2.rectangle(img, (px, py), (px + pw, py + ph), (180, 180, 190), 1)
    cv2.putText(img, "Sign In", (px + 20, py + 40), theme["font_face"], 0.8, (40, 40, 50), 1)
    cv2.putText(img, "Username", (px + 20, py + 80), theme["font_face"], 0.4, (80, 80, 90), 1)
    ux, uy, uw, uh = px + 20, py + 88, pw - 40, 30
    cv2.rectangle(img, (ux, uy), (ux + uw, uy + uh), (255, 255, 255), -1)
    cv2.rectangle(img, (ux, uy), (ux + uw, uy + uh), (200, 200, 210), 1)
    cv2.putText(img, "user@example.com", (ux + 6, uy + 20), theme["font_face"], 0.4, (120, 120, 130), 1)
    elems = [UIElement(4, [ux, uy, uw, uh], "text_field", "username")]
    pw_y = py + 148
    cv2.rectangle(img, (px + 20, pw_y), (px + 20 + uw, pw_y + uh), (255, 255, 255), -1)
    cv2.rectangle(img, (px + 20, pw_y), (px + 20 + uw, pw_y + uh), (200, 200, 210), 1)
    cv2.putText(img, "••••••••", (px + 26, pw_y + 20), theme["font_face"], 0.4, (80, 80, 90), 1)
    elems.append(UIElement(4, [px + 20, pw_y, uw, uh], "text_field", "password"))
    cb_y = pw_y + 45
    cv2.rectangle(img, (px + 22, cb_y), (px + 38, cb_y + 16), (255, 255, 255), -1)
    cv2.rectangle(img, (px + 22, cb_y), (px + 38, cb_y + 16), (150, 150, 160), 1)
    cv2.putText(img, "✓", (px + 24, cb_y + 13), theme["font_face"], 0.4, (60, 60, 180), 1)
    cv2.putText(img, "Remember me", (px + 44, cb_y + 13), theme["font_face"], 0.4, (80, 80, 90), 1)
    elems.append(UIElement(6, [px + 22, cb_y, 16, 16], "checkbox", "remember"))
    btn = draw_button(img, px + 20, py + ph - 55, uw, 32, "Sign In", theme, primary=True)
    elems.append(btn)
    elems.extend(draw_taskbar(img))
    return GeneratedPage(image=img, elements=elems)


def make_toast_notification() -> GeneratedPage:
    """Toast/popup notification from system tray."""
    theme = sample_theme()
    dw, dh = DESKTOP_SIZE
    img = np.ones((dh, dw, 3), dtype=np.uint8) * 200
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = []
    tw, th = 320, 100
    tx, ty = dw - tw - 20, 20
    cv2.rectangle(img, (tx, ty), (tx + tw, ty + th), (255, 255, 255), -1)
    cv2.rectangle(img, (tx, ty), (tx + tw, ty + th), (200, 200, 210), 1)
    cv2.rectangle(img, (tx + 10, ty + 10), (tx + 36, ty + 36), (0, 120, 215), -1)
    elems.append(UIElement(20, [tx + 10, ty + 10, 26, 26], "icon"))
    app = random.choice(["Email", "Calendar", "Slack", "Teams"])
    cv2.putText(img, app, (tx + 44, ty + 24), theme["font_face"], 0.45, (40, 40, 50), 1)
    msg = random.choice(["New message from Alice", "Meeting in 15 minutes", "File upload complete", "Update available"])
    cv2.putText(img, msg, (tx + 10, ty + 60), theme["font_face"], 0.4, (60, 60, 70), 1)
    cv2.putText(img, "×", (tx + tw - 20, ty + 20), theme["font_face"], 0.5, (120, 120, 130), 1)
    elems.append(UIElement(3, [tx + tw - 26, ty + 4, 22, 22], "close_button"))
    for i, icon_name in enumerate(["My Computer", "Recycle Bin", "Documents"]):
        ix, iy = 20 + i * 100, dh - 160
        cv2.rectangle(img, (ix + 15, iy), (ix + 65, iy + 50), (100, 150, 200), -1)
        cv2.putText(img, icon_name, (ix, iy + 70), theme["font_face"], 0.3, (60, 60, 70), 1)
        elems.append(UIElement(20, [ix + 15, iy, 50, 50], "icon"))
    elems.extend(draw_taskbar(img))
    return GeneratedPage(image=img, elements=elems)


def make_data_table() -> GeneratedPage:
    """Data table/grid with headers, rows, sortable columns, and scrollbar."""
    theme = sample_theme()
    dw, dh = DESKTOP_SIZE
    img = np.ones((dh, dw, 3), dtype=np.uint8) * 200
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = draw_taskbar(img)
    ww, wh = 700, 420
    wx, wy = (dw - ww) // 2, 60
    cv2.rectangle(img, (wx, wy), (wx + ww, wy + wh), (250, 250, 255), -1)
    cv2.rectangle(img, (wx, wy), (wx + ww, wy + wh), (180, 180, 190), 1)
    title_h = 28
    cv2.rectangle(img, (wx, wy), (wx + ww, wy + title_h), theme["title_color"], -1)
    cv2.putText(img, "Data Browser", (wx + 8, wy + title_h - 7), theme["font_face"], 0.45, theme["title_text_color"], 1)
    elems.append(UIElement(0, [wx, wy, ww, title_h], "title_bar"))
    tb_y = wy + title_h + 4
    for i, btn_lbl in enumerate(["Add", "Edit", "Delete", "Refresh", "Export"]):
        elems.append(draw_button(img, wx + 8 + i * 70, tb_y, 62, 22, btn_lbl, theme))
    hdr_y = tb_y + 30
    cols, col_widths = ["Name", "Type", "Size", "Modified", "Status"], [160, 100, 80, 140, 100]
    hx = wx + 10
    for _ci, (col, cw) in enumerate(zip(cols, col_widths)):
        cv2.rectangle(img, (hx, hdr_y), (hx + cw, hdr_y + 24), (230, 230, 240), -1)
        cv2.putText(img, col, (hx + 6, hdr_y + 17), theme["font_face"], 0.4, (40, 40, 50), 1)
        hx += cw
    data = [("report_v2.pdf", "PDF", "2.4 MB", "Today 3:45 PM", "Synced"),
            ("screenshot.png", "Image", "856 KB", "Today 2:10 PM", "Synced"),
            ("notes.txt", "Text", "12 KB", "Yesterday", "Modified"),
            ("budget.xlsx", "Sheet", "48 KB", "Jun 24", "Modified"),
            ("presentation.pptx", "Slides", "3.1 MB", "Jun 23", "New"),
            ("archive.zip", "Archive", "15.6 MB", "Jun 22", "Uploading"),
            ("config.json", "JSON", "4 KB", "Jun 21", "Synced"),
            ("backup.db", "DB", "128 MB", "Jun 20", "Synced")]
    for ri, (name, ftype, size, date, status) in enumerate(data):
        row_y = hdr_y + 24 + ri * 24
        row_color = (245, 245, 250) if ri % 2 == 0 else (250, 250, 255)
        cv2.rectangle(img, (wx + 10, row_y), (wx + ww - 30, row_y + 24), row_color, -1)
        hx = wx + 10
        for vi, (val, cw) in enumerate(zip([name, ftype, size, date, status], col_widths)):
            cv2.putText(img, val, (hx + 6, row_y + 17), theme["font_face"], 0.35, (60, 60, 70), 1)
            hx += cw
            if vi == 0:
                elems.append(UIElement(14, [hx - cw, row_y, cw, 24], "list_item", name))
    sb_y, sb_h = hdr_y, len(data) * 24
    cv2.rectangle(img, (wx + ww - 22, sb_y), (wx + ww - 10, sb_y + sb_h), (230, 230, 240), -1)
    cv2.rectangle(img, (wx + ww - 22, sb_y), (wx + ww - 10, sb_y + 60), (180, 180, 195), -1)
    elems.append(UIElement(13, [wx + ww - 22, sb_y, 12, sb_h], "scrollbar"))
    return GeneratedPage(image=img, elements=elems)


def make_drag_drop() -> GeneratedPage:
    """Drag-and-drop interface with file list and drop target."""
    theme = sample_theme()
    dw, dh = DESKTOP_SIZE
    img = np.ones((dh, dw, 3), dtype=np.uint8) * 200
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = draw_taskbar(img)
    ww, wh = 640, 400
    wx, wy = (dw - ww) // 2, 80
    cv2.rectangle(img, (wx, wy), (wx + ww, wy + wh), (248, 248, 252), -1)
    cv2.rectangle(img, (wx, wy), (wx + ww, wy + wh), (180, 180, 190), 1)
    title_h = 28
    cv2.rectangle(img, (wx, wy), (wx + ww, wy + title_h), theme["title_color"], -1)
    cv2.putText(img, "File Upload", (wx + 8, wy + title_h - 7), theme["font_face"], 0.45, theme["title_text_color"], 1)
    elems.append(UIElement(0, [wx, wy, ww, title_h], "title_bar"))
    ct = wy + title_h + 20
    sx, sy, sw, sh = wx + 20, ct, 260, wh - 80
    cv2.rectangle(img, (sx, sy), (sx + sw, sy + sh), (240, 240, 248), -1)
    cv2.rectangle(img, (sx, sy), (sx + sw, sy + sh), (200, 200, 210), 1)
    cv2.putText(img, "Files to upload", (sx + 8, sy + 20), theme["font_face"], 0.4, (40, 40, 50), 1)
    for fi, fn in enumerate(["document.pdf", "image.png", "data.csv", "presentation.pptx", "notes.txt"]):
        fy = sy + 32 + fi * 36
        cv2.rectangle(img, (sx + 8, fy), (sx + sw - 8, fy + 30), (255, 255, 255), -1)
        cv2.rectangle(img, (sx + 8, fy), (sx + sw - 8, fy + 30), (210, 210, 220), 1)
        cv2.rectangle(img, (sx + 12, fy + 4), (sx + 26, fy + 26), (80, 140, 200), -1)
        cv2.putText(img, fn, (sx + 34, fy + 20), theme["font_face"], 0.35, (40, 40, 50), 1)
        elems.append(UIElement(20, [sx + 12, fy + 4, 14, 22], "icon"))
    tx, ty, tw, th = sx + sw + 30, ct, 260, wh - 80
    cv2.rectangle(img, (tx, ty), (tx + tw, ty + th), (235, 248, 240), -1)
    cv2.rectangle(img, (tx, ty), (tx + tw, ty + th), (120, 200, 140), 2)
    cv2.putText(img, "Drop files here", (tx + 50, ty + th // 2 - 10), theme["font_face"], 0.5, (80, 140, 100), 1)
    cv2.putText(img, "or click to browse", (tx + 45, ty + th // 2 + 15), theme["font_face"], 0.35, (120, 160, 130), 1)
    elems.append(UIElement(2, [tx, ty, tw, th], "button", "drop_zone"))
    elems.append(draw_button(img, wx + ww - 120, wh - 45, 100, 28, "Upload All", theme, primary=True))
    return GeneratedPage(image=img, elements=elems)


def make_loading_screen() -> GeneratedPage:
    """Loading/progress dialog with progress bar and spinner."""
    theme = sample_theme()
    dw, dh = DESKTOP_SIZE
    img = np.ones((dh, dw, 3), dtype=np.uint8) * 200
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = draw_taskbar(img)
    dlw, dlh = 400, 180
    dlx, dly = (dw - dlw) // 2, (dh - dlh) // 2
    cv2.rectangle(img, (dlx, dly), (dlx + dlw, dly + dlh), (255, 255, 255), -1)
    cv2.rectangle(img, (dlx, dly), (dlx + dlw, dly + dlh), (180, 180, 190), 1)
    title_h = 28
    cv2.rectangle(img, (dlx, dly), (dlx + dlw, dly + title_h), theme["title_color"], -1)
    cv2.putText(img, "Processing", (dlx + 8, dly + title_h - 7), theme["font_face"], 0.45, theme["title_text_color"], 1)
    elems.append(UIElement(0, [dlx, dly, dlw, title_h], "title_bar"))
    sx, sy = dlx + 30, dly + title_h + 30
    for angle in range(0, 360, 30):
        rad = np.radians(angle)
        cv2.circle(img, (int(sx + 15 * np.cos(rad)), int(sy + 15 * np.sin(rad))), 3, (80, 140, 200), -1)
    status = random.choice(["Installing components...", "Downloading updates...", "Extracting files...", "Please wait..."])
    cv2.putText(img, status, (dlx + 70, dly + title_h + 37), theme["font_face"], 0.45, (60, 60, 70), 1)
    pb_x, pb_y, pb_w, pb_h = dlx + 30, dly + title_h + 60, dlw - 60, 20
    cv2.rectangle(img, (pb_x, pb_y), (pb_x + pb_w, pb_y + pb_h), (220, 220, 230), -1)
    progress = random.randint(30, 90)
    cv2.rectangle(img, (pb_x, pb_y), (pb_x + int(pb_w * progress / 100), pb_y + pb_h), (0, 120, 215), -1)
    elems.append(UIElement(16, [pb_x, pb_y, pb_w, pb_h], "progress_bar"))
    cv2.putText(img, f"{progress}% complete", (dlx + 30, dly + title_h + 100), theme["font_face"], 0.35, (100, 100, 110), 1)
    elems.append(draw_button(img, dlx + dlw - 90, dly + dlh - 40, 70, 26, "Cancel", theme))
    return GeneratedPage(image=img, elements=elems)


GENERATORS = [
    ("save_dialog", make_save_dialog),
    ("settings", make_settings_window),
    ("error_dialog", make_error_dialog),
    ("notepad", make_notepad_window),
    ("control_panel", make_control_panel),
    ("file_manager", make_file_manager),
    ("multi_window", make_multi_window),
    ("browser", make_browser),
    ("terminal", make_terminal),
    ("context_menu", make_context_menu),
    ("wizard", make_wizard),
    ("find_replace", make_find_replace),
    ("print_dialog", make_print_dialog),
    ("about_dialog", make_about_dialog),
    ("file_properties", make_file_properties),
    ("system_tray", make_system_tray_popup),
    ("form_fill", make_form_fill),
    ("login", make_login_screen),
    ("toast", make_toast_notification),
    ("data_table", make_data_table),
    ("drag_drop", make_drag_drop),
    ("loading", make_loading_screen),
]


# ── Output methods ──────────────────────────────────────────────────────

def yolo_label(element: UIElement, img_w: int, img_h: int) -> str:
    """Convert UIElement to YOLO format string.

    Coordinates are clamped to [0, 1] to prevent out-of-bounds labels
    from elements that extend past the image edge (e.g., taskbars at
    the bottom edge, dialog shadows at the right edge).
    """
    x, y, bw, bh = element.bbox
    cx = (x + bw / 2) / img_w
    cy = (y + bh / 2) / img_h
    nw = bw / img_w
    nh = bh / img_h
    # Clamp to valid [0, 1] range — elements past the image edge get
    # their center pulled inward so the box is still learnable.
    cx = max(0.0, min(1.0, cx))
    cy = max(0.0, min(1.0, cy))
    nw = max(0.001, min(1.0, nw))
    nh = max(0.001, min(1.0, nh))
    return f"{element.cls_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}"


def add_wine_softness(img: np.ndarray) -> np.ndarray:
    """Add subtle blur to simulate Wine's softer font rendering."""
    if random.random() < 0.8:
        sigma = random.uniform(0.1, 0.5)
        img = cv2.GaussianBlur(img, (3, 3), sigma)
    return img


def add_noise(img: np.ndarray) -> np.ndarray:
    """Add subtle noise to simulate compression artifacts."""
    sigma = random.uniform(0.5, 5.0)
    noise = np.random.normal(0, sigma, img.shape).astype(np.int16)
    img = img.astype(np.int16) + noise
    return np.clip(img, 0, 255).astype(np.uint8)


def variation(img: np.ndarray) -> np.ndarray:
    """Apply aggressive random variations for robust cross-domain generalization."""
    # HSV jitter (saturation + value = color shifts across rendering engines)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    if random.random() < 0.9:
        hsv[:, :, 1] *= random.uniform(0.6, 1.4)   # saturation ±40%
    if random.random() < 0.9:
        hsv[:, :, 2] *= random.uniform(0.7, 1.3)    # brightness ±30%
    img = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)
    # Contrast
    if random.random() < 0.7:
        alpha = random.uniform(0.7, 1.3)
        img = cv2.convertScaleAbs(img, alpha=alpha, beta=random.randint(-30, 30))
    # Resolution variation: occasionally scale down and back up
    if random.random() < 0.5:
        scale = random.uniform(0.6, 1.0)
        h, w = img.shape[:2]
        small = cv2.resize(img, (int(w*scale), int(h*scale)))
        img = cv2.resize(small, (w, h))
    return img


def dict_name(name: str, prefix: str, suffix: str) -> str:
    """Convert snake_case to display text: save_dialog -> Save Dialog."""
    return name.replace("_", " ").title()


# ── Interaction state indicators ────────────────────────────────────────

CURSOR_TYPES = {
    "arrow":        [(0,0), (1,0), (4,1), (3,2), (4,3), (2,4), (0,5), (1,8), (0,9), (-1,9)],
    "ibeam":        [(0,2),(1,2),(0,8),(1,8)],
    "hand":         [(0,0),(2,1),(4,3),(3,5),(1,6),(0,5),(-1,5)],
}
CURSOR_DRAW_POINTS = {
    "arrow":  [(8,1),(14,10),(12,12),(8,6),(1,14),(0,12),(6,7),(3,4),(7,3)],
    "ibeam":  [(5,1),(7,1),(7,13),(5,13)],
    "hand":   [(2,1),(4,4),(9,7),(8,10),(4,10),(3,8),(0,8)],
}

def draw_cursor(img, x, y):
    """Draw mouse cursor icon at position."""
    ctype = random.choice(list(CURSOR_DRAW_POINTS.keys()))
    pts = np.array(CURSOR_DRAW_POINTS[ctype], dtype=np.int32) + [x, y]
    cv2.fillPoly(img, [pts], (255, 255, 255))
    cv2.polylines(img, [pts], True, (0, 0, 0), 1)
    return UIElement(20, [x - 2, y - 2, 24, 24], "icon", f"cursor_{ctype}")

def draw_text_caret(img, x, y, h):
    """Draw blinking text cursor in a text field."""
    if random.random() < 0.5:  # 50% chance caret visible (blinking simulation)
        cv2.line(img, (x, y + 2), (x, y + h - 2), (0, 0, 0), 2)
    return UIElement(20, [x - 1, y, 3, h], "icon", "text_caret")

def draw_focus_rect(img, x, y, w, h):
    """Draw dotted focus rectangle around focused element."""
    for i in range(x + 2, x + w - 2, 4):
        cv2.line(img, (i, y + 1), (min(i + 2, x + w - 2), y + 1), (50, 50, 50), 1)
        if y + h > 1:
            cv2.line(img, (i, max(y + 1, 0)), (min(i + 2, 0), 0), (50, 50, 50), 1)

def draw_tooltip(img, x, y, text):
    """Draw yellow tooltip near cursor/button."""
    tw = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)[0][0]
    bw, bh = tw + 12, 20
    if x + bw > img.shape[1]: x = img.shape[1] - bw - 4
    if y - bh < 0: y = y + bh + 16
    cv2.rectangle(img, (x, y - bh), (x + bw, y), (255, 255, 225), -1)
    cv2.rectangle(img, (x, y - bh), (x + bw, y), (180, 180, 100), 1)
    cv2.putText(img, text, (x + 6, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
    return UIElement(11, [x, y - bh, bw, bh], "dialog", f"tooltip_{text}")

def draw_notification(img, text):
    """Draw notification toast in bottom-right corner."""
    w, h = img.shape[1], img.shape[0]
    tw = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[0][0]
    bw, bh = tw + 24, 36
    nx, ny = w - bw - 20, h - TASKBAR_HEIGHT - bh - 10
    cv2.rectangle(img, (nx, ny), (nx + bw, ny + bh), (50, 50, 55), -1)
    cv2.rectangle(img, (nx, ny), (nx + bw, ny + bh), (80, 80, 100), 1)
    cv2.putText(img, text, (nx + 12, ny + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)
    return UIElement(11, [nx, ny, bw, bh], "dialog", f"notification_{text}")

def add_interaction_state(img, elements, theme):
    """Add random interaction state indicators to a generated page."""
    new_elems = []

    # Random cursor position on the screen
    if random.random() < 0.6:
        cx = random.randint(100, img.shape[1] - 100)
        cy = random.randint(50, img.shape[0] - 100)
        new_elems.append(draw_cursor(img, cx, cy))
        # Tooltip near cursor 20% of time
        if random.random() < 0.2:
            tips = ["Save", "Open", "Copy", "Help", "Properties", "Delete"]
            new_elems.append(draw_tooltip(img, cx + 12, cy - 8, random.choice(tips)))

    # Text caret in a text field
    text_fields = [e for e in elements if e.cls_id == 4]
    if text_fields and random.random() < 0.7:
        tf = random.choice(text_fields)
        bx, by, bw, bh = tf.bbox
        caret_x = bx + random.randint(4, min(12, bw - 4))
        new_elems.append(draw_text_caret(img, caret_x, by + 2, bh - 4))

    # Focus rectangle on active element
    focusable = [e for e in elements if e.cls_id in (2, 4, 5)]
    if focusable and random.random() < 0.4:
        fe = random.choice(focusable)
        bx, by, bw, bh = fe.bbox
        draw_focus_rect(img, bx - 2, by - 2, bw + 4, bh + 4)

    # Notification toast
    if random.random() < 0.15:
        msgs = ["Update available", "File saved", "Download complete",
                "Connection established", "3 new messages"]
        new_elems.append(draw_notification(img, random.choice(msgs)))

    # Selection highlight on some text
    list_items = [e for e in elements if e.cls_id == 14]
    if list_items and random.random() < 0.5:
        li = random.choice(list_items)
        bx, by, bw, bh = li.bbox
        overlay = img[by:by+bh, bx:bx+bw].copy()
        overlay[:, :, 0] = cv2.addWeighted(overlay[:, :, 0], 0.6, np.full_like(overlay[:, :, 0], 200), 0.4, 0)
        img[by:by+bh, bx:bx+bw] = overlay

    # Disable some buttons (grayed out + dimmed)
    buttons = [e for e in elements if e.cls_id == 2]
    for btn in random.sample(buttons, min(len(buttons), random.randint(0, 2))):
        bx, by, bw, bh = btn.bbox
        if bh < 2 or bw < 2:
            continue
        overlay = img[by:by+bh, bx:bx+bw].copy()
        if overlay.size == 0:
            continue
        overlay = cv2.cvtColor(overlay, cv2.COLOR_BGR2GRAY)
        overlay = cv2.cvtColor(overlay, cv2.COLOR_GRAY2BGR)
        overlay = cv2.convertScaleAbs(overlay, alpha=0.6, beta=30)
        img[by:by+bh, bx:bx+bw] = overlay
        btn.label = f"{btn.label}_disabled"

    return new_elems


# ── Main generator ──────────────────────────────────────────────────────

# Resolution variants for cross-resolution robustness
TARGET_RESOLUTIONS = [
    (1280, 720), (1024, 768), (1366, 768), (1440, 900), (1920, 1080)
]
# DPI scaling factors (render large, then downscale)
DPI_SCALES = [1.0, 1.25, 1.0, 1.5, 1.0, 1.0, 1.75, 1.0, 1.0, 1.0]  # ~30% chance of fractional scaling


def generate_dataset(output_dir: str, count: int, seed: int = 42,
                     split: str = "all"):
    """Generate a full labeled dataset with cross-resolution and font variation.

    Args:
        output_dir: Root output directory.
        count: Total images to generate (distributed across scenes).
        seed: Random seed for reproducibility.
        split: "train", "val", "test", or "all" (uses all scenes).
    """
    random.seed(seed)
    np.random.seed(seed)

    # Set split for theme sampling (controls which frameworks are available)
    set_split(split)

    # Filter generators by split
    allowed_scenes = _get_split_scenes(split)
    generators = [(n, f) for n, f in GENERATORS if n in allowed_scenes]
    if not generators:
        print(f"ERROR: No generators for split '{split}'", file=sys.stderr)
        return {"classes": WINE_CLASSES, "images": []}

    if split != "all":
        img_dir = os.path.join(output_dir, split, "images")
        lbl_dir = os.path.join(output_dir, split, "labels")
    else:
        img_dir = os.path.join(output_dir, "images")
        lbl_dir = os.path.join(output_dir, "labels")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(lbl_dir, exist_ok=True)

    manifest = {"classes": WINE_CLASSES, "split": split, "images": []}
    ocr_entries = []

    per_generator = max(1, count // len(generators))
    img_idx = 0

    for gen_name, gen_fn in generators:
        for i in range(per_generator):
            # Random resolution + DPI for cross-platform robustness
            base_res = random.choice(TARGET_RESOLUTIONS)
            dpi_scale = random.choice(DPI_SCALES)
            render_w = int(base_res[0] * dpi_scale)
            render_h = int(base_res[1] * dpi_scale)

            # Override desktop size for this generation
            global DESKTOP_SIZE
            old_size = DESKTOP_SIZE
            DESKTOP_SIZE = (render_w, render_h)

            page = gen_fn()
            img = page.image  # mutable reference to the page image

            # Restore desktop size
            DESKTOP_SIZE = old_size

            # Randomly apply window state variation (inactive, maximized, minimized)
            window_state = random.choice(WINDOW_STATES)
            if gen_name in ("settings", "notepad", "control_panel", "file_manager"):
                # These scenes have identifiable windows to modify
                # Apply state to the primary window (find by title bar element)
                title_bars = [e for e in page.elements if e.cls_id == 0]
                if title_bars and window_state != "active":
                    tb = title_bars[0]
                    page.elements = apply_window_state(
                        img, page.elements, tb.bbox[0], tb.bbox[1],
                        max(tb.bbox[2], 300), max(tb.bbox[3], 200),
                        window_state, theme=None
                    )

            # Randomly add desktop icons in empty space
            if random.random() < 0.4:
                icons = ["My Computer", "Recycle Bin", "Documents", "Network", "Setup"]
                for _k, icon in enumerate(random.sample(icons, random.randint(2, 4))):
                    ix, iy = random.randint(10, 400), random.randint(10, 600)
                    cv2.rectangle(img, (ix, iy), (ix + 18, iy + 18),
                                  random.choice([(0, 120, 200), (200, 160, 0), (100, 100, 100)]), -1)
                    font, scale, thick = get_font()
                    cv2.putText(img, icon, (ix - 6, iy + 34), font, scale * 0.4, (255, 255, 255), thick)
                    page.elements.append(UIElement(20, [ix - 6, iy + 18, 50, 20], "icon", icon))

            # Add interaction state indicators (cursor, caret, focus, tooltips, etc.)
            page.elements += add_interaction_state(img, page.elements, theme=None)

            # Apply Wine rendering variations
            img = page.image.astype(np.float32)
            if WINE_SOFTNESS > 0:
                img = cv2.GaussianBlur(img, (3, 3), WINE_SOFTNESS)
            img = add_noise(img.astype(np.uint8))
            img = variation(img)

            # If rendered at higher DPI, downscale to target training size
            if render_w != 1280 or render_h != 720:
                # Scale bounding boxes proportionally
                scale_x = 1280.0 / render_w
                scale_y = 720.0 / render_h
                for elem in page.elements:
                    bx, by, bw, bh = elem.bbox
                    elem.bbox = [
                        int(bx * scale_x), int(by * scale_y),
                        int(bw * scale_x), int(bh * scale_y),
                    ]
                img = cv2.resize(img.astype(np.uint8), (1280, 720))

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

            # Collect OCR ground truth from UI elements
            for elem in page.elements:
                if elem.ocr_text:
                    ocr_entries.append({
                        "image": img_name,
                        "text": elem.ocr_text,
                        "bbox": elem.bbox,
                        "source": "ui_element",
                        "class": WINE_CLASSES[elem.cls_id],
                        "confidence": 100,
                    })
            # Collect OCR ground truth from content text (not UI elements —
            # e.g. notepad text lines, file names in lists)
            for gt in page.ground_truth_texts:
                ocr_entries.append({
                    "image": img_name,
                    "text": gt.get("text", ""),
                    "bbox": gt.get("bbox", [0, 0, 0, 0]),
                    "source": "content_text",
                    "class": "text",
                    "confidence": 100,
                })

            manifest["images"].append({
                "file": img_name,
                "generator": gen_name,
                "resolution": f"{render_w}x{render_h}@{dpi_scale}x",
                "elements": len(page.elements),
                "ocr_texts": sum(1 for e in page.elements if e.ocr_text),
            })

            img_idx += 1
            if img_idx % 50 == 0:
                print(f"  {img_idx}/{count} images...")

    # Write data.yaml for YOLO training (only for "train" or "all" splits)
    if split in ("train", "all"):
        yaml_path = os.path.join(output_dir, "data.yaml")
        train_ref = f"{split}/images" if split != "all" else "images"
        val_ref = "val/images" if os.path.isdir(os.path.join(output_dir, "val", "images")) else train_ref
        with open(yaml_path, "w") as f:
            f.write(f"# WineBot Ground Truth Dataset — {split} split, {img_idx} images\n")
            f.write(f"# Split info: train={TRAIN_SCENES}, val={VAL_SCENES}, test={TEST_SCENES}\n")
            f.write(f"path: {output_dir}\n")
            f.write(f"train: {train_ref}\n")
            f.write(f"val: {val_ref}\n")
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

    print(f"\nDataset generated: {img_idx} images ({split} split)")
    print(f"  Images: {img_dir}/")
    print(f"  Labels: {lbl_dir}/")
    if split in ("train", "all"):
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
    parser.add_argument("--split", default="all",
                        choices=["train", "val", "test", "all"],
                        help="Dataset split: train/val/test scenes + held-out frameworks")
    args = parser.parse_args()

    allowed = _get_split_scenes(args.split)
    print(f"WineBot Ground Truth Generator — {args.split.upper()} split")
    print(f"  Output: {args.output}")
    print(f"  Images: {args.count}")
    print(f"  Classes: {len(WINE_CLASSES)}")
    print(f"  Scenes: {len(allowed)} ({', '.join(allowed)})")
    print(f"  Frameworks: {len(_get_split_frameworks(args.split))}")
    print()

    generate_dataset(args.output, args.count, args.seed, args.split)


if __name__ == "__main__":
    main()
