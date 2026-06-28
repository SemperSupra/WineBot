#!/usr/bin/env python3
"""Oversample scenes containing low-F1 classes to balance class distribution.

Low-F1 classes and their source scenes:
- spinner_button: print_dialog (1/scene)
- icon: error_dialog, about_dialog, file_properties (1/scene each)
- progress_bar: control_panel (1/scene)
- status_bar: notepad, form_fill (1/scene each)
- radio: print_dialog(4), settings(3), wizard(1)

Strategy: Generate 5× more images of scenes containing rare classes.
"""
import importlib.util
import json
import os
import random
import time

import cv2

spec = importlib.util.spec_from_file_location("winebot_gt", "/scripts/winebot-gt-generator.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

OUTPUT_DIR = "/models/wine-dataset-10k-oversampled"
BASE_IMAGES = 100  # images per scene for common classes
OVERSAMPLE = {
    "print_dialog": 500,     # 5× for spinner_button + radio
    "settings": 500,         # 5× for radio
    "wizard": 500,           # 5× for radio
    "control_panel": 500,    # 5× for progress_bar
    "notepad": 500,          # 5× for status_bar
    "form_fill": 500,        # 5× for status_bar
    "error_dialog": 500,     # 5× for icon
    "about_dialog": 500,     # 5× for icon
    "file_properties": 500,  # 5× for icon
}

GENERATORS = [
    ("save_dialog", gen.make_save_dialog, 100),
    ("settings", gen.make_settings_window, 500),       # 5× for radio
    ("error_dialog", gen.make_error_dialog, 500),       # 5× for icon
    ("notepad", gen.make_notepad_window, 500),          # 5× for status_bar
    ("control_panel", gen.make_control_panel, 500),     # 5× for progress_bar
    ("file_manager", gen.make_file_manager, 100),
    ("multi_window", gen.make_multi_window, 100),
    ("browser", gen.make_browser, 100),
    ("terminal", gen.make_terminal, 100),
    ("context_menu", gen.make_context_menu, 100),
    ("wizard", gen.make_wizard, 500),                  # 5× for radio
    ("about_dialog", gen.make_about_dialog, 500),      # 5× for icon
    ("file_properties", gen.make_file_properties, 500), # 5× for icon
    ("system_tray", gen.make_system_tray_popup, 100),
    ("form_fill", gen.make_form_fill, 500),             # 5× for status_bar
    ("find_replace", gen.make_find_replace, 100),
    ("print_dialog", gen.make_print_dialog, 500),       # 5× for spinner + radio
]

CLASS_NAMES = {0:'title_bar',1:'title_text',2:'button',3:'close_button',
    4:'text_field',5:'dropdown',6:'checkbox',7:'radio',8:'menu_bar',
    9:'menu_item',10:'taskbar',11:'dialog',12:'text_area',13:'scrollbar',
    14:'list_item',15:'tab',16:'progress_bar',17:'toolbar',18:'status_bar',
    19:'link',20:'icon',21:'spinner_button'}
LOW_F1 = {5: 'radio', 16: 'progress_bar', 18: 'status_bar', 19: 'link', 20: 'icon', 21: 'spinner_button'}

RESOLUTIONS = [(1024, 768), (1280, 720), (1366, 768), (1440, 900), (1920, 1080)]


def main():
    gen.set_split("all")
    os.makedirs(f"{OUTPUT_DIR}/images", exist_ok=True)
    os.makedirs(f"{OUTPUT_DIR}/labels", exist_ok=True)

    manifest = []
    total = 0
    rare_counts = {}

    print("Generating oversampled dataset...\n")
    t0 = time.time()

    for scene_name, scene_fn, count in GENERATORS:
        scene_t0 = time.time()
        scene_count = 0

        for _i in range(count):
            gen.DESKTOP_SIZE = random.choice(RESOLUTIONS)
            page = scene_fn()
            img = page.image
            if img is None:
                continue

            fname = f"{scene_name}_{total:06d}.png"
            cv2.imwrite(os.path.join(OUTPUT_DIR, "images", fname), img)

            h, w = img.shape[:2]
            with open(os.path.join(OUTPUT_DIR, "labels", f"{scene_name}_{total:06d}.txt"), "w") as lf:
                for elem in page.elements:
                    lf.write(gen.yolo_label(elem, w, h) + "\n")
                    if elem.cls_id in LOW_F1:
                        rare_counts[LOW_F1[elem.cls_id]] = rare_counts.get(LOW_F1[elem.cls_id], 0) + 1

            manifest.append({"file": fname, "generator": scene_name, "elements": len(page.elements)})
            total += 1
            scene_count += 1

        print(f"  {scene_name:<20s} {scene_count:>4d} images  {time.time()-scene_t0:>4.1f}s")

    with open(os.path.join(OUTPUT_DIR, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nTotal: {total} images in {time.time()-t0:.0f}s")
    print("\nRare class counts:")
    for cls, count in sorted(rare_counts.items()):
        print(f"  {cls:<20s} {count:>6d}")


if __name__ == "__main__":
    main()
