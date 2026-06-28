#!/usr/bin/env python3
"""Generate balanced labeled dataset for screen state classifier.

Calls GT generator functions directly, saves images with scene type
metadata in a manifest file.

Usage:
  docker exec winebot-cv python3 /tmp/generate_state_data.py
"""
import importlib.util
import json
import os
import random
import time

import cv2

# Import GT generator (hyphenated filename)
spec = importlib.util.spec_from_file_location(
    "winebot_gt", "/scripts/winebot-gt-generator.py"
)
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

OUTPUT_DIR = "/models/state-dataset"
IMAGES_PER_SCENE = 200  # 15 × 200 = 3,000 images

# Map scene names to generator functions
GENERATORS = [
    ("save_dialog", gen.make_save_dialog),
    ("settings", gen.make_settings_window),
    ("error_dialog", gen.make_error_dialog),
    ("notepad", gen.make_notepad_window),
    ("control_panel", gen.make_control_panel),
    ("file_manager", gen.make_file_manager),
    ("multi_window", gen.make_multi_window),
    ("browser", gen.make_browser),
    ("terminal", gen.make_terminal),
    ("context_menu", gen.make_context_menu),
    ("wizard", gen.make_wizard),
    ("about_dialog", gen.make_about_dialog),
    ("file_properties", gen.make_file_properties),
    ("system_tray", gen.make_system_tray_popup),
    ("form_fill", gen.make_form_fill),
    ("find_replace", gen.make_find_replace),
    ("print_dialog", gen.make_print_dialog),
    ("login", gen.make_login_screen),
    ("toast", gen.make_toast_notification),
    ("data_table", gen.make_data_table),
    ("drag_drop", gen.make_drag_drop),
    ("loading", gen.make_loading_screen),
]

# Resolutions for variation
RESOLUTIONS = [(1024, 768), (1280, 720), (1366, 768), (1440, 900), (1920, 1080)]


def main():
    os.makedirs(f"{OUTPUT_DIR}/images", exist_ok=True)

    # Unlock all scene types
    gen.set_split("all")

    manifest = []
    total = 0

    print(f"Generating {IMAGES_PER_SCENE} images per scene type...")
    t0 = time.time()

    for scene_name, scene_fn in GENERATORS:
        scene_t0 = time.time()
        scene_count = 0

        for i in range(IMAGES_PER_SCENE):
            # Vary resolution for robustness
            gen.DESKTOP_SIZE = random.choice(RESOLUTIONS)

            # Generate scene
            page = scene_fn()
            img = page.image
            if img is None:
                continue

            # Save image
            fname = f"{scene_name}_{total:06d}.png"
            fpath = os.path.join(OUTPUT_DIR, "images", fname)
            cv2.imwrite(fpath, img)
            total += 1
            scene_count += 1

            manifest.append({
                "file": fname,
                "generator": scene_name,
                "elements": len(page.elements),
                "resolution": f"{img.shape[1]}x{img.shape[0]}",
            })

        elapsed = time.time() - scene_t0
        rate = scene_count / elapsed if elapsed > 0 else 0
        print(f"  {scene_name:<20s} {scene_count:>3d} images  {elapsed:>5.1f}s  {rate:>4.0f} img/s")

    # Save manifest
    manifest_path = os.path.join(OUTPUT_DIR, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    total_elapsed = time.time() - t0
    print(f"\nDone! {total} images in {total_elapsed:.0f}s ({total/total_elapsed:.0f} img/s)")
    print(f"  Images:   {OUTPUT_DIR}/images/")
    print(f"  Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
