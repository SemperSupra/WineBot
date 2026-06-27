#!/usr/bin/env python3
"""Additional scene generators for Wine desktop GT dataset.

Adds 5 missing scene types: login, toast notification, data table,
drag-and-drop, and loading screen.
"""
import importlib.util, random

import cv2
import numpy as np

# Import existing generator utilities
spec = importlib.util.spec_from_file_location(
    "winebot_gt", "/scripts/diagnostics/winebot-gt-generator.py"
)
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

# Reuse existing helpers
UIElement = gen.UIElement
GeneratedPage = gen.GeneratedPage
sample_theme = gen.sample_theme
draw_taskbar = gen.draw_taskbar
draw_button = gen.draw_button
DESKTOP_SIZE = lambda: gen.DESKTOP_SIZE
DESKTOP_BG_THEMES = gen.DESKTOP_BG_THEMES


def make_login_screen() -> GeneratedPage:
    """Login/authentication screen with username, password, and submit."""
    theme = sample_theme()
    dw, dh = gen.DESKTOP_SIZE
    img = np.ones((dh, dw, 3), dtype=np.uint8) * 60

    # Background gradient effect
    overlay = img.copy()
    cv2.rectangle(overlay, (0, 0), (dw, dh), (70, 70, 90), -1)
    cv2.addWeighted(overlay, 0.3, img, 0.7, 0, img)

    # Login panel
    pw, ph = 340, 320
    px, py = (dw - pw) // 2, (dh - ph) // 2 - 40
    cv2.rectangle(img, (px, py), (px + pw, py + ph), (240, 240, 245), -1)
    cv2.rectangle(img, (px, py), (px + pw, py + ph), (180, 180, 190), 1)

    # Title
    cv2.putText(img, "Sign In", (px + 20, py + 40), theme["font_face"],
                0.8, (40, 40, 50), 1)

    # Username field
    cv2.putText(img, "Username", (px + 20, py + 80), theme["font_face"],
                0.4, (80, 80, 90), 1)
    ux, uy, uw, uh = px + 20, py + 88, pw - 40, 30
    cv2.rectangle(img, (ux, uy), (ux + uw, uy + uh), (255, 255, 255), -1)
    cv2.rectangle(img, (ux, uy), (ux + uw, uy + uh), (200, 200, 210), 1)
    cv2.putText(img, "user@example.com", (ux + 6, uy + 20),
                theme["font_face"], 0.4, (120, 120, 130), 1)
    elems = [UIElement(4, [ux, uy, uw, uh], "text_field", "username")]

    # Password field
    cv2.putText(img, "Password", (px + 20, py + 140), theme["font_face"],
                0.4, (80, 80, 90), 1)
    pw_y = py + 148
    cv2.rectangle(img, (px + 20, pw_y), (px + 20 + uw, pw_y + uh), (255, 255, 255), -1)
    cv2.rectangle(img, (px + 20, pw_y), (px + 20 + uw, pw_y + uh), (200, 200, 210), 1)
    cv2.putText(img, "••••••••", (px + 26, pw_y + 20), theme["font_face"],
                0.4, (80, 80, 90), 1)
    elems.append(UIElement(4, [px + 20, pw_y, uw, uh], "text_field", "password"))

    # Remember me checkbox
    cb_y = pw_y + 45
    cv2.rectangle(img, (px + 22, cb_y), (px + 38, cb_y + 16), (255, 255, 255), -1)
    cv2.rectangle(img, (px + 22, cb_y), (px + 38, cb_y + 16), (150, 150, 160), 1)
    cv2.putText(img, "✓", (px + 24, cb_y + 13), theme["font_face"],
                0.4, (60, 60, 180), 1)
    cv2.putText(img, "Remember me", (px + 44, cb_y + 13), theme["font_face"],
                0.4, (80, 80, 90), 1)
    elems.append(UIElement(6, [px + 22, cb_y, 16, 16], "checkbox", "remember"))

    # Login button
    btn = draw_button(img, px + 20, py + ph - 55, uw, 32, "Sign In", theme, primary=True)
    elems.append(btn)

    # Taskbar
    elems.extend(draw_taskbar(img))

    return GeneratedPage(image=img, elements=elems)


def make_toast_notification() -> GeneratedPage:
    """Toast/popup notification from system tray."""
    theme = sample_theme()
    dw, dh = gen.DESKTOP_SIZE
    img = np.ones((dh, dw, 3), dtype=np.uint8) * 200
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = []

    # Toast notification (top-right corner)
    tw, th = 320, 100
    tx, ty = dw - tw - 20, 20
    cv2.rectangle(img, (tx, ty), (tx + tw, ty + th), (255, 255, 255), -1)
    cv2.rectangle(img, (tx, ty), (tx + tw, ty + th), (200, 200, 210), 1)

    # App icon
    cv2.rectangle(img, (tx + 10, ty + 10), (tx + 36, ty + 36), (0, 120, 215), -1)
    elems.append(UIElement(20, [tx + 10, ty + 10, 26, 26], "icon"))

    # Title
    app = random.choice(["Email", "Calendar", "Slack", "Teams"])
    cv2.putText(img, app, (tx + 44, ty + 24), theme["font_face"],
                0.45, (40, 40, 50), 1)

    # Message
    msg = random.choice([
        "New message from Alice",
        "Meeting in 15 minutes",
        "File upload complete",
        "Update available",
    ])
    cv2.putText(img, msg, (tx + 10, ty + 60), theme["font_face"],
                0.4, (60, 60, 70), 1)

    # Close button
    cv2.putText(img, "×", (tx + tw - 20, ty + 20), theme["font_face"],
                0.5, (120, 120, 130), 1)
    elems.append(UIElement(3, [tx + tw - 26, ty + 4, 22, 22], "close_button"))

    # Desktop icons on the desktop area
    for i, icon_name in enumerate(["My Computer", "Recycle Bin", "Documents"]):
        ix, iy = 20 + i * 100, dh - 160
        cv2.rectangle(img, (ix + 15, iy), (ix + 65, iy + 50), (100, 150, 200), -1)
        cv2.putText(img, icon_name, (ix, iy + 70), theme["font_face"],
                    0.3, (60, 60, 70), 1)
        elems.append(UIElement(20, [ix + 15, iy, 50, 50], "icon"))

    elems.extend(draw_taskbar(img))
    return GeneratedPage(image=img, elements=elems)


def make_data_table() -> GeneratedPage:
    """Data table/grid with headers, sortable columns, and scrollbar."""
    theme = sample_theme()
    dw, dh = gen.DESKTOP_SIZE
    img = np.ones((dh, dw, 3), dtype=np.uint8) * 200
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = draw_taskbar(img)

    # Window
    ww, wh = 700, 420
    wx, wy = (dw - ww) // 2, 60
    cv2.rectangle(img, (wx, wy), (wx + ww, wy + wh), (250, 250, 255), -1)
    cv2.rectangle(img, (wx, wy), (wx + ww, wy + wh), (180, 180, 190), 1)

    # Title bar
    title_h = 28
    cv2.rectangle(img, (wx, wy), (wx + ww, wy + title_h), theme["title_color"], -1)
    cv2.putText(img, "Data Browser", (wx + 8, wy + title_h - 7),
                theme["font_face"], 0.45, theme["title_text_color"], 1)
    elems.append(UIElement(0, [wx, wy, ww, title_h], "title_bar"))

    # Toolbar
    tb_y = wy + title_h + 4
    for i, btn_lbl in enumerate(["Add", "Edit", "Delete", "Refresh", "Export"]):
        bx = wx + 8 + i * 70
        btn = draw_button(img, bx, tb_y, 62, 22, btn_lbl, theme)
        elems.append(btn)

    # Table header
    hdr_y = tb_y + 30
    cols = ["Name", "Type", "Size", "Modified", "Status"]
    col_widths = [160, 100, 80, 140, 100]
    hx = wx + 10
    for ci, (col, cw) in enumerate(zip(cols, col_widths)):
        cv2.rectangle(img, (hx, hdr_y), (hx + cw, hdr_y + 24), (230, 230, 240), -1)
        cv2.putText(img, col, (hx + 6, hdr_y + 17), theme["font_face"],
                    0.4, (40, 40, 50), 1)
        if ci == 0:
            cv2.putText(img, "▼", (hx + cw - 18, hdr_y + 17), theme["font_face"],
                        0.3, (60, 60, 180), 1)  # sort indicator
        hx += cw
    elems.append(UIElement(15, [wx + 10, hdr_y, sum(col_widths), 24], "tab", "header"))

    # Table rows
    data = [
        ("report_v2.pdf", "PDF Document", "2.4 MB", "Today 3:45 PM", "Synced"),
        ("screenshot.png", "PNG Image", "856 KB", "Today 2:10 PM", "Synced"),
        ("notes.txt", "Text Document", "12 KB", "Yesterday", "Modified"),
        ("budget.xlsx", "Spreadsheet", "48 KB", "Jun 24", "Modified"),
        ("presentation.pptx", "Presentation", "3.1 MB", "Jun 23", "New"),
        ("archive.zip", "Compressed", "15.6 MB", "Jun 22", "Uploading"),
        ("config.json", "JSON File", "4 KB", "Jun 21", "Synced"),
        ("backup.db", "Database", "128 MB", "Jun 20", "Synced"),
    ]
    for ri, (name, ftype, size, date, status) in enumerate(data):
        row_y = hdr_y + 24 + ri * 24
        row_color = (245, 245, 250) if ri % 2 == 0 else (250, 250, 255)
        cv2.rectangle(img, (wx + 10, row_y), (wx + ww - 30, row_y + 24), row_color, -1)
        hx = wx + 10
        vals = [name, ftype, size, date, status]
        for vi, (val, cw) in enumerate(zip(vals, col_widths)):
            cv2.putText(img, val, (hx + 6, row_y + 17), theme["font_face"],
                        0.35, (60, 60, 70), 1)
            hx += cw
            if vi == 0:
                elems.append(UIElement(14, [hx - cw, row_y, cw, 24], "list_item", name))
            elif vi == 4:
                elems.append(UIElement(19, [hx - cw, row_y, cw, 24], "link", status))

    # Scrollbar
    sb_y = hdr_y
    sb_h = len(data) * 24
    cv2.rectangle(img, (wx + ww - 22, sb_y), (wx + ww - 10, sb_y + sb_h), (230, 230, 240), -1)
    cv2.rectangle(img, (wx + ww - 22, sb_y), (wx + ww - 10, sb_y + 60), (180, 180, 195), -1)
    elems.append(UIElement(13, [wx + ww - 22, sb_y, 12, sb_h], "scrollbar"))

    return GeneratedPage(image=img, elements=elems)


def make_drag_drop() -> GeneratedPage:
    """Drag-and-drop interface with source panel and target area."""
    theme = sample_theme()
    dw, dh = gen.DESKTOP_SIZE
    img = np.ones((dh, dw, 3), dtype=np.uint8) * 200
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = draw_taskbar(img)

    # Window
    ww, wh = 640, 400
    wx, wy = (dw - ww) // 2, 80
    cv2.rectangle(img, (wx, wy), (wx + ww, wy + wh), (248, 248, 252), -1)
    cv2.rectangle(img, (wx, wy), (wx + ww, wy + wh), (180, 180, 190), 1)

    title_h = 28
    cv2.rectangle(img, (wx, wy), (wx + ww, wy + title_h), theme["title_color"], -1)
    cv2.putText(img, "File Upload", (wx + 8, wy + title_h - 7),
                theme["font_face"], 0.45, theme["title_text_color"], 1)
    elems.append(UIElement(0, [wx, wy, ww, title_h], "title_bar"))

    content_top = wy + title_h + 20

    # Source panel: list of files
    src_x, src_y, src_w, src_h = wx + 20, content_top, 260, wh - 80
    cv2.rectangle(img, (src_x, src_y), (src_x + src_w, src_y + src_h),
                  (240, 240, 248), -1)
    cv2.rectangle(img, (src_x, src_y), (src_x + src_w, src_y + src_h),
                  (200, 200, 210), 1)
    cv2.putText(img, "Files to upload", (src_x + 8, src_y + 20),
                theme["font_face"], 0.4, (40, 40, 50), 1)

    files = ["document.pdf", "image.png", "data.csv", "presentation.pptx", "notes.txt"]
    for fi, fn in enumerate(files):
        fy = src_y + 32 + fi * 36
        cv2.rectangle(img, (src_x + 8, fy), (src_x + src_w - 8, fy + 30),
                      (255, 255, 255), -1)
        cv2.rectangle(img, (src_x + 8, fy), (src_x + src_w - 8, fy + 30),
                      (210, 210, 220), 1)
        # File icon
        cv2.rectangle(img, (src_x + 12, fy + 4), (src_x + 26, fy + 26),
                      (80, 140, 200), -1)
        cv2.putText(img, fn, (src_x + 34, fy + 20), theme["font_face"],
                    0.35, (40, 40, 50), 1)
        elems.append(UIElement(20, [src_x + 12, fy + 4, 14, 22], "icon"))
        elems.append(UIElement(14, [src_x + 8, fy, src_w - 16, 30], "list_item", fn))

    # Target area (drop zone)
    tgt_x = src_x + src_w + 30
    tgt_y, tgt_w, tgt_h = content_top, 260, wh - 80
    cv2.rectangle(img, (tgt_x, tgt_y), (tgt_x + tgt_w, tgt_y + tgt_h),
                  (235, 248, 240), -1)
    cv2.rectangle(img, (tgt_x, tgt_y), (tgt_x + tgt_w, tgt_y + tgt_h),
                  (120, 200, 140), 2, 2)
    cv2.putText(img, "Drop files here", (tgt_x + 50, tgt_y + tgt_h // 2 - 10),
                theme["font_face"], 0.5, (80, 140, 100), 1)
    cv2.putText(img, "or click to browse", (tgt_x + 45, tgt_y + tgt_h // 2 + 15),
                theme["font_face"], 0.35, (120, 160, 130), 1)
    elems.append(UIElement(2, [tgt_x, tgt_y, tgt_w, tgt_h], "button", "drop_zone"))

    # Upload button
    btn = draw_button(img, wx + ww - 120, wh - 45, 100, 28, "Upload All", theme, primary=True)
    elems.append(btn)

    return GeneratedPage(image=img, elements=elems)


def make_loading_screen() -> GeneratedPage:
    """Loading/progress screen with progress bar and status text."""
    theme = sample_theme()
    dw, dh = gen.DESKTOP_SIZE
    img = np.ones((dh, dw, 3), dtype=np.uint8) * 200
    img[:] = random.choice(DESKTOP_BG_THEMES)
    elems = draw_taskbar(img)

    # Dialog
    dlw, dlh = 400, 180
    dlx, dly = (dw - dlw) // 2, (dh - dlh) // 2
    cv2.rectangle(img, (dlx, dly), (dlx + dlw, dly + dlh), (255, 255, 255), -1)
    cv2.rectangle(img, (dlx, dly), (dlx + dlw, dly + dlh), (180, 180, 190), 1)

    # Title bar
    title_h = 28
    cv2.rectangle(img, (dlx, dly), (dlx + dlw, dly + title_h), theme["title_color"], -1)
    cv2.putText(img, "Processing", (dlx + 8, dly + title_h - 7),
                theme["font_face"], 0.45, theme["title_text_color"], 1)
    elems.append(UIElement(0, [dlx, dly, dlw, title_h], "title_bar"))

    # Spinner animation (simulated)
    spinner_x, spinner_y = dlx + 30, dly + title_h + 30
    for angle in range(0, 360, 30):
        rad = np.radians(angle)
        sx = int(spinner_x + 15 * np.cos(rad))
        sy = int(spinner_y + 15 * np.sin(rad))
        cv2.circle(img, (sx, sy), 3, (80, 140, 200), -1)

    # Status text
    status = random.choice([
        "Installing components...",
        "Downloading updates...",
        "Extracting files...",
        "Configuring settings...",
        "Please wait...",
    ])
    cv2.putText(img, status, (dlx + 70, dly + title_h + 37),
                theme["font_face"], 0.45, (60, 60, 70), 1)

    # Progress bar
    pb_x, pb_y, pb_w, pb_h = dlx + 30, dly + title_h + 60, dlw - 60, 20
    cv2.rectangle(img, (pb_x, pb_y), (pb_x + pb_w, pb_y + pb_h), (220, 220, 230), -1)
    progress = random.randint(30, 90)
    cv2.rectangle(img, (pb_x, pb_y), (pb_x + int(pb_w * progress / 100), pb_y + pb_h),
                  (0, 120, 215), -1)
    elems.append(UIElement(16, [pb_x, pb_y, pb_w, pb_h], "progress_bar"))

    # Progress text
    cv2.putText(img, f"{progress}% complete", (dlx + 30, dly + title_h + 100),
                theme["font_face"], 0.35, (100, 100, 110), 1)

    # Cancel button
    btn = draw_button(img, dlx + dlw - 90, dly + dlh - 40, 70, 26, "Cancel", theme)
    elems.append(btn)

    return GeneratedPage(image=img, elements=elems)


# Register new generators
NEW_GENERATORS = [
    ("login", make_login_screen),
    ("toast", make_toast_notification),
    ("data_table", make_data_table),
    ("drag_drop", make_drag_drop),
    ("loading", make_loading_screen),
]
