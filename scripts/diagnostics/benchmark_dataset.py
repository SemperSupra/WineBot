#!/usr/bin/env python3
"""Generate synthetic UI test images with known ground truth for OCR/detection benchmarking.

Produces images with precisely known text and UI element positions so we can
measure accuracy (not just speed). Each image has a manifest with expected text,
element bounding boxes, and UI types.

Usage:
  python3 scripts/diagnostics/benchmark_dataset.py --output /path/to/dataset
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np

# ── Ground-truth image definitions ──────────────────────────────────────────

def _make_dialog_with_buttons(size: Tuple = (1280, 720)) -> Tuple[np.ndarray, Dict]:
    """Standard Windows-style dialog with title bar, buttons, and text."""
    w, h = size
    img = np.ones((h, w, 3), dtype=np.uint8) * 240  # Light gray background

    # Dialog window
    dialog_x, dialog_y = 200, 100
    dialog_w, dialog_h = 880, 520
    cv2.rectangle(img, (dialog_x, dialog_y), (dialog_x + dialog_w, dialog_y + dialog_h),
                  (255, 255, 255), -1)  # White dialog
    cv2.rectangle(img, (dialog_x, dialog_y), (dialog_x + dialog_w, dialog_y + dialog_h),
                  (180, 180, 180), 2)  # Border

    # Title bar
    title_h = 28
    cv2.rectangle(img, (dialog_x, dialog_y), (dialog_x + dialog_w, dialog_y + title_h),
                  (0, 120, 215), -1)  # Windows blue
    cv2.putText(img, "Save As", (dialog_x + 12, dialog_y + 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1, cv2.LINE_AA)

    # Close button
    close_x = dialog_x + dialog_w - 36
    cv2.rectangle(img, (close_x, dialog_y + 4), (close_x + 28, dialog_y + 22),
                  (200, 50, 50), -1)
    cv2.putText(img, "X", (close_x + 8, dialog_y + 19),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

    # File name label
    label_y = dialog_y + title_h + 30
    cv2.putText(img, "File name:", (dialog_x + 20, label_y + 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (50, 50, 50), 1, cv2.LINE_AA)

    # Text field
    tf_x, tf_y = dialog_x + 130, label_y
    tf_w, tf_h = 500, 26
    cv2.rectangle(img, (tf_x, tf_y), (tf_x + tf_w, tf_y + tf_h), (255, 255, 255), -1)
    cv2.rectangle(img, (tf_x, tf_y), (tf_x + tf_w, tf_y + tf_h), (120, 120, 120), 1)
    cv2.putText(img, "document.txt", (tf_x + 6, tf_y + 19),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)

    # Save as type label
    type_label_y = tf_y + tf_h + 25
    cv2.putText(img, "Save as type:", (dialog_x + 20, type_label_y + 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (50, 50, 50), 1, cv2.LINE_AA)

    # Dropdown
    dd_x, dd_y = dialog_x + 130, type_label_y
    dd_w, dd_h = 200, 26
    cv2.rectangle(img, (dd_x, dd_y), (dd_x + dd_w, dd_y + dd_h), (255, 255, 255), -1)
    cv2.rectangle(img, (dd_x, dd_y), (dd_x + dd_w, dd_y + dd_h), (120, 120, 120), 1)
    cv2.putText(img, "Text Documents (*.txt)", (dd_x + 6, dd_y + 19),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

    # Buttons
    btn_y = dialog_y + dialog_h - 50
    save_btn = (dialog_x + dialog_w - 220, btn_y, 90, 30)
    cancel_btn = (dialog_x + dialog_w - 120, btn_y, 90, 30)

    for bx, by, bw, bh, text, color in [
        (*save_btn, "Save", (0, 150, 0)),
        (*cancel_btn, "Cancel", (180, 180, 180)),
    ]:
        cv2.rectangle(img, (bx, by), (bx + bw, by + bh), color, -1)
        cv2.rectangle(img, (bx, by), (bx + bw, by + bh), (100, 100, 100), 1)
        tw = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)[0][0]
        cv2.putText(img, text, (bx + (bw - tw) // 2, by + 21),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

    # Hide button
    hide_btn = (dialog_x + dialog_w - 340, btn_y, 90, 30)
    cv2.rectangle(img, (hide_btn[0], hide_btn[1]), (hide_btn[0] + hide_btn[2], hide_btn[1] + hide_btn[3]),
                  (180, 180, 180), -1)
    cv2.rectangle(img, (hide_btn[0], hide_btn[1]), (hide_btn[0] + hide_btn[2], hide_btn[1] + hide_btn[3]),
                  (100, 100, 100), 1)
    cv2.putText(img, "Hide Folders", (hide_btn[0] + 4, hide_btn[1] + 21),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (50, 50, 50), 1, cv2.LINE_AA)

    # Sidebar
    sidebar_x = dialog_x + 15
    sidebar_y = dialog_y + title_h + 10
    sidebar_entries = ["Desktop", "Documents", "Downloads", "Music", "Pictures"]
    for i, entry in enumerate(sidebar_entries):
        cy = sidebar_y + i * 28
        cv2.putText(img, entry, (sidebar_x + 5, cy + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (30, 30, 30), 1, cv2.LINE_AA)

    ground_truth = {
        "description": "Windows Save As dialog with title bar, text field, dropdown, buttons, sidebar",
        "expected_text": [
            "Save As", "File name:", "document.txt", "Save as type:",
            "Text Documents (*.txt)", "Save", "Cancel", "Hide Folders",
            "Desktop", "Documents", "Downloads", "Music", "Pictures",
        ],
        "expected_elements": [
            {"type": "title_bar", "bbox": [dialog_x, dialog_y, dialog_w, title_h]},
            {"type": "button", "bbox": [close_x, dialog_y + 4, 28, 22], "label": "X"},
            {"type": "text_field", "bbox": [tf_x, tf_y, tf_w, tf_h]},
            {"type": "dropdown", "bbox": [dd_x, dd_y, dd_w, dd_h]},
            {"type": "button", "bbox": [*save_btn], "label": "Save"},
            {"type": "button", "bbox": [*cancel_btn], "label": "Cancel"},
            {"type": "button", "bbox": [*hide_btn], "label": "Hide Folders"},
        ],
        "ui_state": "dialog_visible",
    }
    return img, ground_truth


def _make_menu_bar(size: Tuple = (1280, 720)) -> Tuple[np.ndarray, Dict]:
    """Application window with standard menu bar (File, Edit, View, Help)."""
    w, h = size
    img = np.ones((h, w, 3), dtype=np.uint8) * 200  # Desktop background

    # Window
    win_x, win_y = 150, 80
    win_w, win_h = 980, 560
    cv2.rectangle(img, (win_x, win_y), (win_x + win_w, win_y + win_h),
                  (255, 255, 255), -1)
    cv2.rectangle(img, (win_x, win_y), (win_x + win_w, win_y + win_h),
                  (150, 150, 150), 2)

    # Title bar
    title_h = 28
    cv2.rectangle(img, (win_x, win_y), (win_x + win_w, win_y + title_h),
                  (0, 120, 215), -1)
    cv2.putText(img, "Untitled - Notepad", (win_x + 10, win_y + 21),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1, cv2.LINE_AA)

    # Menu bar
    menu_y = win_y + title_h
    menu_h = 22
    cv2.rectangle(img, (win_x, menu_y), (win_x + win_w, menu_y + menu_h),
                  (245, 245, 245), -1)
    menus = ["File", "Edit", "Format", "View", "Help"]
    menu_elements = []
    cx = win_x + 8
    for menu_name in menus:
        tw = cv2.getTextSize(menu_name, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)[0][0]
        cv2.putText(img, menu_name, (cx, menu_y + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (30, 30, 30), 1, cv2.LINE_AA)
        menu_elements.append({"type": "menu_bar", "bbox": [cx, menu_y, tw + 10, menu_h], "label": menu_name})
        cx += tw + 16

    # Text area
    text_x = win_x + 5
    text_y = menu_y + menu_h + 3
    text_w = win_w - 10
    text_h = win_h - menu_h - title_h - 8
    cv2.rectangle(img, (text_x, text_y), (text_x + text_w, text_y + text_h),
                  (255, 255, 255), -1)
    cv2.rectangle(img, (text_x, text_y), (text_x + text_w, text_y + text_h),
                  (200, 200, 200), 1)

    # Sample text
    lines = [
        "Hello World!",
        "This is a test document.",
        "Line three of content.",
        "WineBot automation testing.",
        "",
        "The quick brown fox jumps over the lazy dog.",
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "abcdefghijklmnopqrstuvwxyz",
        "0123456789",
    ]
    for i, line in enumerate(lines):
        cv2.putText(img, line, (text_x + 8, text_y + 22 + i * 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

    ground_truth = {
        "description": "Notepad-style application with menu bar and text content",
        "expected_text": ["Untitled - Notepad"] + menus + lines,
        "expected_elements": [
            {"type": "title_bar", "bbox": [win_x, win_y, win_w, title_h]},
            {"type": "menu_bar", "bbox": [win_x, menu_y, win_w, menu_h]},
            {"type": "text_area", "bbox": [text_x, text_y, text_w, text_h]},
        ] + menu_elements,
        "ui_state": "text_editor_visible",
    }
    return img, ground_truth


def _make_error_dialog(size: Tuple = (1280, 720)) -> Tuple[np.ndarray, Dict]:
    """Windows error/information dialog."""
    w, h = size
    img = np.ones((h, w, 3), dtype=np.uint8) * 200

    # Centered dialog
    dlg_w, dlg_h = 420, 180
    dlg_x = (w - dlg_w) // 2
    dlg_y = (h - dlg_h) // 2
    cv2.rectangle(img, (dlg_x, dlg_y), (dlg_x + dlg_w, dlg_y + dlg_h),
                  (255, 255, 255), -1)
    cv2.rectangle(img, (dlg_x, dlg_y), (dlg_x + dlg_w, dlg_y + dlg_h),
                  (150, 150, 150), 2)

    # Title
    title_h = 28
    cv2.rectangle(img, (dlg_x, dlg_y), (dlg_x + dlg_w, dlg_y + title_h),
                  (0, 120, 215), -1)
    cv2.putText(img, "Error", (dlg_x + 10, dlg_y + 21),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1, cv2.LINE_AA)

    # Error icon (simplified X in circle)
    icon_cx, icon_cy = dlg_x + 40, dlg_y + title_h + 50
    cv2.circle(img, (icon_cx, icon_cy), 22, (200, 50, 50), 2)

    # Error message
    cv2.putText(img, "The operation completed successfully.", (dlg_x + 75, dlg_y + title_h + 38),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.putText(img, "Click OK to continue.", (dlg_x + 75, dlg_y + title_h + 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (80, 80, 80), 1, cv2.LINE_AA)

    # OK button
    ok_x = dlg_x + dlg_w - 100
    ok_y = dlg_y + dlg_h - 42
    ok_w, ok_h = 80, 28
    cv2.rectangle(img, (ok_x, ok_y), (ok_x + ok_w, ok_y + ok_h),
                  (0, 120, 215), -1)
    cv2.rectangle(img, (ok_x, ok_y), (ok_x + ok_w, ok_y + ok_h),
                  (0, 80, 160), 1)
    cv2.putText(img, "OK", (ok_x + 28, ok_y + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

    ground_truth = {
        "description": "Windows error message dialog with title, icon, text, and OK button",
        "expected_text": [
            "Error", "The operation completed successfully.",
            "Click OK to continue.", "OK",
        ],
        "expected_elements": [
            {"type": "title_bar", "bbox": [dlg_x, dlg_y, dlg_w, title_h]},
            {"type": "dialog", "bbox": [dlg_x, dlg_y, dlg_w, dlg_h]},
            {"type": "button", "bbox": [ok_x, ok_y, ok_w, ok_h], "label": "OK"},
        ],
        "ui_state": "dialog_visible",
    }
    return img, ground_truth


def _make_settings_window(size: Tuple = (1280, 720)) -> Tuple[np.ndarray, Dict]:
    """Settings dialog with checkboxes, radio buttons, sliders."""
    w, h = size
    img = np.ones((h, w, 3), dtype=np.uint8) * 200

    win_x, win_y = 250, 100
    win_w, win_h = 780, 520
    cv2.rectangle(img, (win_x, win_y), (win_x + win_w, win_y + win_h),
                  (255, 255, 255), -1)
    cv2.rectangle(img, (win_x, win_y), (win_x + win_w, win_y + win_h),
                  (150, 150, 150), 2)

    # Title
    cv2.rectangle(img, (win_x, win_y), (win_x + win_w, win_y + 28),
                  (0, 120, 215), -1)
    cv2.putText(img, "Settings", (win_x + 10, win_y + 21),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1, cv2.LINE_AA)

    elements = [{"type": "title_bar", "bbox": [win_x, win_y, win_w, 28]}]

    # Tabs (simplified)
    tab_y = win_y + 40
    tabs = ["General", "Display", "Audio", "Network", "Advanced"]
    tx = win_x + 20
    for tab in tabs:
        tw = cv2.getTextSize(tab, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0]
        cv2.rectangle(img, (tx, tab_y), (tx + tw + 16, tab_y + 24), (230, 230, 230), -1)
        cv2.rectangle(img, (tx, tab_y), (tx + tw + 16, tab_y + 24), (180, 180, 180), 1)
        cv2.putText(img, tab, (tx + 8, tab_y + 17),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (30, 30, 30), 1, cv2.LINE_AA)
        elements.append({"type": "button", "bbox": [tx, tab_y, tw + 16, 24], "label": tab})
        tx += tw + 22

    # Checkboxes
    cb_y = tab_y + 50
    checkboxes = [
        "Enable notifications",
        "Start with system",
        "Check for updates automatically",
        "Send anonymous usage data",
    ]
    for i, cb_label in enumerate(checkboxes):
        by = cb_y + i * 32
        cv2.rectangle(img, (win_x + 30, by), (win_x + 48, by + 18), (255, 255, 255), -1)
        cv2.rectangle(img, (win_x + 30, by), (win_x + 48, by + 18), (100, 100, 100), 2)
        if i < 2:  # First two checked
            cv2.line(img, (win_x + 33, by + 9), (win_x + 39, by + 15), (0, 150, 0), 2)
            cv2.line(img, (win_x + 39, by + 15), (win_x + 46, by + 4), (0, 150, 0), 2)
        cv2.putText(img, cb_label, (win_x + 58, by + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (30, 30, 30), 1, cv2.LINE_AA)
        elements.append({"type": "checkbox", "bbox": [win_x + 30, by, 18, 18], "label": cb_label})

    # OK/Cancel/Apply buttons at bottom
    btn_y = win_y + win_h - 45
    for bx, label, color in [
        (win_x + win_w - 290, "Apply", (180, 180, 180)),
        (win_x + win_w - 190, "Cancel", (180, 180, 180)),
        (win_x + win_w - 100, "OK", (0, 120, 215)),
    ]:
        bw, bh = 80, 28
        cv2.rectangle(img, (bx, btn_y), (bx + bw, btn_y + bh), color, -1)
        cv2.rectangle(img, (bx, btn_y), (bx + bw, btn_y + bh), (100, 100, 100), 1)
        text_color = (255, 255, 255) if color == (0, 120, 215) else (50, 50, 50)
        tw = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0]
        cv2.putText(img, label, (bx + (bw - tw) // 2, btn_y + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, text_color, 1, cv2.LINE_AA)
        elements.append({"type": "button", "bbox": [bx, btn_y, bw, bh], "label": label})

    ground_truth = {
        "description": "Settings dialog with tabs, checkboxes, and action buttons",
        "expected_text": [
            "Settings", "General", "Display", "Audio", "Network", "Advanced",
            "Enable notifications", "Start with system",
            "Check for updates automatically", "Send anonymous usage data",
            "Apply", "Cancel", "OK",
        ],
        "expected_elements": elements,
        "ui_state": "dialog_visible",
    }
    return img, ground_truth


def _make_installer_window(size: Tuple = (1280, 720)) -> Tuple[np.ndarray, Dict]:
    """Windows installer wizard with Next/Cancel buttons and progress."""
    w, h = size
    img = np.ones((h, w, 3), dtype=np.uint8) * 200

    win_x, win_y = 180, 80
    win_w, win_h = 920, 560
    cv2.rectangle(img, (win_x, win_y), (win_x + win_w, win_y + win_h),
                  (255, 255, 255), -1)
    cv2.rectangle(img, (win_x, win_y), (win_x + win_w, win_y + win_h),
                  (150, 150, 150), 2)

    # Title
    cv2.rectangle(img, (win_x, win_y), (win_x + win_w, win_y + 28),
                  (0, 120, 215), -1)
    cv2.putText(img, "7-Zip 24.09 Setup", (win_x + 10, win_y + 21),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1, cv2.LINE_AA)

    elements = [{"type": "title_bar", "bbox": [win_x, win_y, win_w, 28]}]

    # Welcome text
    cy = win_y + 60
    cv2.putText(img, "Welcome to the 7-Zip Setup Wizard", (win_x + 40, cy),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2, cv2.LINE_AA)
    cv2.putText(img, "This will install 7-Zip 24.09 (x64 edition) on your computer.", (win_x + 40, cy + 32),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50, 50, 50), 1, cv2.LINE_AA)
    cv2.putText(img, "It is recommended that you close all other applications before continuing.", (win_x + 40, cy + 56),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50, 50, 50), 1, cv2.LINE_AA)

    # License agreement (simplified)
    lic_y = cy + 90
    cv2.putText(img, "License Agreement", (win_x + 40, lic_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
    lic_box = (win_x + 40, lic_y + 10, win_w - 80, 200)
    cv2.rectangle(img, (lic_box[0], lic_box[1]), (lic_box[0] + lic_box[2], lic_box[1] + lic_box[3]),
                  (250, 250, 250), -1)
    cv2.rectangle(img, (lic_box[0], lic_box[1]), (lic_box[0] + lic_box[2], lic_box[1] + lic_box[3]),
                  (180, 180, 180), 1)

    for i, line in enumerate([
        "7-Zip is free software licensed under the GNU LGPL.",
        "",
        "You may freely use, copy, and distribute 7-Zip",
        "subject to the terms of the GNU LGPL license.",
        "",
        "7-Zip Copyright (C) 1999-2024 Igor Pavlov.",
    ]):
        cv2.putText(img, line, (lic_box[0] + 8, lic_box[1] + 22 + i * 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (30, 30, 30), 1, cv2.LINE_AA)

    # I accept radio
    radio_y = lic_box[1] + lic_box[3] + 15
    cv2.circle(img, (win_x + 55, radio_y + 8), 8, (100, 100, 100), 1)
    cv2.circle(img, (win_x + 55, radio_y + 8), 4, (0, 150, 0), -1)  # Selected
    cv2.putText(img, "I accept the agreement", (win_x + 72, radio_y + 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    elements.append({"type": "radio", "bbox": [win_x + 40, radio_y, 250, 24], "label": "I accept the agreement"})

    # Next/Cancel buttons
    btn_y = win_y + win_h - 45
    for bx, label, color in [
        (win_x + win_w - 190, "Cancel", (200, 200, 200)),
        (win_x + win_w - 100, "Next >", (0, 120, 215)),
    ]:
        bw, bh = 80, 28
        cv2.rectangle(img, (bx, btn_y), (bx + bw, btn_y + bh), color, -1)
        cv2.rectangle(img, (bx, btn_y), (bx + bw, btn_y + bh), (100, 100, 100), 1)
        text_color = (255, 255, 255) if color == (0, 120, 215) else (50, 50, 50)
        tw = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0]
        cv2.putText(img, label, (bx + (bw - tw) // 2, btn_y + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, text_color, 1, cv2.LINE_AA)
        elements.append({"type": "button", "bbox": [bx, btn_y, bw, bh], "label": label})

    ground_truth = {
        "description": "Installer wizard with license text, radio button, Next/Cancel buttons",
        "expected_text": [
            "7-Zip 24.09 Setup", "Welcome to the 7-Zip Setup Wizard",
            "License Agreement", "I accept the agreement",
            "Cancel", "Next >",
        ],
        "expected_elements": elements,
        "ui_state": "dialog_visible",
    }
    return img, ground_truth


def _make_dense_ui(size: Tuple = (1280, 720)) -> Tuple[np.ndarray, Dict]:
    """Complex UI with many buttons, text fields, and labels."""
    w, h = size
    img = np.ones((h, w, 3), dtype=np.uint8) * 200

    # Toolbar window
    win_x, win_y = 100, 60
    win_w, win_h = 1080, 600
    cv2.rectangle(img, (win_x, win_y), (win_x + win_w, win_y + win_h),
                  (240, 240, 240), -1)
    cv2.rectangle(img, (win_x, win_y), (win_x + win_w, win_y + win_h),
                  (150, 150, 150), 2)

    # Title
    cv2.rectangle(img, (win_x, win_y), (win_x + win_w, win_y + 28),
                  (50, 50, 50), -1)
    cv2.putText(img, "WineBot Control Panel", (win_x + 10, win_y + 21),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1, cv2.LINE_AA)

    elements = [{"type": "title_bar", "bbox": [win_x, win_y, win_w, 28]}]

    # Toolbar buttons
    tb_y = win_y + 36
    tools = ["New", "Open", "Save", "Cut", "Copy", "Paste", "Undo", "Redo"]
    tx = win_x + 12
    for tool in tools:
        tw = cv2.getTextSize(tool, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[0][0]
        bw = max(tw + 12, 40)
        cv2.rectangle(img, (tx, tb_y), (tx + bw, tb_y + 26), (255, 255, 255), -1)
        cv2.rectangle(img, (tx, tb_y), (tx + bw, tb_y + 26), (180, 180, 180), 1)
        cv2.putText(img, tool, (tx + 6, tb_y + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (30, 30, 30), 1, cv2.LINE_AA)
        elements.append({"type": "button", "bbox": [tx, tb_y, bw, 26], "label": tool})
        tx += bw + 6

    # Sidebar
    sb_x = win_x + 10
    sb_y = tb_y + 40
    sb_w = 180
    cv2.rectangle(img, (sb_x, sb_y), (sb_x + sb_w, sb_y + 400), (230, 230, 230), -1)
    cv2.rectangle(img, (sb_x, sb_y), (sb_x + sb_w, sb_y + 400), (180, 180, 180), 1)

    for i, item in enumerate(["Dashboard", "Sessions", "Analysis", "Settings", "Logs", "About"]):
        iy = sb_y + 8 + i * 32
        cv2.rectangle(img, (sb_x + 4, iy), (sb_x + sb_w - 8, iy + 26), (210, 210, 210), -1)
        cv2.putText(img, item, (sb_x + 14, iy + 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (30, 30, 30), 1, cv2.LINE_AA)
        elements.append({"type": "button", "bbox": [sb_x + 4, iy, sb_w - 8, 26], "label": item})

    # Main content area — form fields
    form_x = sb_x + sb_w + 20
    form_y = sb_y + 10
    fields = [
        ("Session Name:", "winebot-session-001"),
        ("API Endpoint:", "http://localhost:8000"),
        ("Auth Token:", "••••••••••••••••"),
        ("Recording Mode:", "continuous"),
        ("Output Directory:", "/artifacts/sessions/"),
        ("Frame Rate:", "1.0 fps"),
        ("Max Duration:", "600s"),
    ]
    for i, (label, value) in enumerate(fields):
        fy = form_y + i * 36
        cv2.putText(img, label, (form_x, fy + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50, 50, 50), 1, cv2.LINE_AA)
        fw, fh = 320, 24
        fx = form_x + 170
        cv2.rectangle(img, (fx, fy), (fx + fw, fy + fh), (255, 255, 255), -1)
        cv2.rectangle(img, (fx, fy), (fx + fw, fy + fh), (150, 150, 150), 1)
        cv2.putText(img, value, (fx + 6, fy + 17),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
        elements.append({"type": "text_field", "bbox": [fx, fy, fw, fh], "label": label.strip(":")})

    # Start/Stop buttons
    btn_y = form_y + len(fields) * 36 + 20
    for bx, label, color in [
        (form_x, "Start Recording", (0, 160, 0)),
        (form_x + 150, "Stop Recording", (180, 50, 50)),
        (form_x + 300, "Reset", (180, 180, 180)),
    ]:
        bw, bh = 130, 32
        cv2.rectangle(img, (bx, btn_y), (bx + bw, btn_y + bh), color, -1)
        cv2.rectangle(img, (bx, btn_y), (bx + bw, btn_y + bh), (100, 100, 100), 1)
        tc = (255, 255, 255) if color != (180, 180, 180) else (30, 30, 30)
        tw = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0]
        cv2.putText(img, label, (bx + (bw - tw) // 2, btn_y + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, tc, 1, cv2.LINE_AA)
        elements.append({"type": "button", "bbox": [bx, btn_y, bw, bh], "label": label})

    ground_truth = {
        "description": "WineBot control panel with toolbar, sidebar, form fields, action buttons",
        "expected_text": [
            "WineBot Control Panel",
        ] + tools + ["Dashboard", "Sessions", "Analysis", "Settings", "Logs", "About"] +
        [f[0] for f in fields] + ["Start Recording", "Stop Recording", "Reset"],
        "expected_elements": elements,
        "ui_state": "interactive_ui_visible",
    }
    return img, ground_truth


# ── Generator registry ────────────────────────────────────────────────────

GENERATORS = {
    "dialog_saveas": _make_dialog_with_buttons,
    "notepad_menu": _make_menu_bar,
    "error_dialog": _make_error_dialog,
    "settings": _make_settings_window,
    "installer": _make_installer_window,
    "dense_ui": _make_dense_ui,
}


def generate_dataset(output_dir: str, generate_all: bool = True):
    """Generate all synthetic benchmark images with ground truth manifests."""
    os.makedirs(output_dir, exist_ok=True)

    manifest = {"dataset": "winebot-benchmark-v1", "images": []}

    for name, generator in GENERATORS.items():
        img_path = os.path.join(output_dir, f"{name}.png")
        img, gt = generator()

        cv2.imwrite(img_path, img)

        entry = {
            "name": name,
            "path": img_path,
            "size": list(img.shape[:2]),
            "ground_truth": gt,
        }
        manifest["images"].append(entry)
        print(f"  Generated: {name}.png ({img.shape[1]}x{img.shape[0]}) — "
              f"{len(gt['expected_text'])} texts, {len(gt['expected_elements'])} elements")

    # Write manifest
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nDataset: {len(manifest['images'])} images → {output_dir}")
    print(f"Manifest: {manifest_path}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Generate WineBot benchmark dataset")
    parser.add_argument("--output", default="/tmp/benchmark_dataset",
                        help="Output directory for images + manifest")
    args = parser.parse_args()

    generate_dataset(args.output)


if __name__ == "__main__":
    main()
