#!/usr/bin/env python3
"""Generate a stratified evaluation dataset for pipeline benchmarking.

Ensures all 22 UI element classes have sufficient samples (N >= 30)
for statistically meaningful per-class metrics.

Usage:
  docker exec winebot-cv python3 /tmp/generate_eval_dataset.py
"""
import importlib.util
import json
import os
import random
import time
from collections import Counter

import cv2

# Import GT generator
spec = importlib.util.spec_from_file_location(
    "winebot_gt", "/scripts/winebot-gt-generator.py"
)
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

OUTPUT_DIR = "/models/eval-dataset"
SAMPLES_PER_SCENE = 100  # 17 scenes × 100 = 1,700 images
SCENE_TYPES = [
    "save_dialog", "settings", "error_dialog", "notepad",
    "control_panel", "file_manager", "multi_window", "browser",
    "terminal", "context_menu", "wizard", "find_replace",
    "print_dialog", "about_dialog", "file_properties",
    "system_tray", "form_fill",
]

CLASS_NAMES = {0:'title_bar',1:'title_text',2:'button',3:'close_button',
    4:'text_field',5:'dropdown',6:'checkbox',7:'radio',8:'menu_bar',
    9:'menu_item',10:'taskbar',11:'dialog',12:'text_area',13:'scrollbar',
    14:'list_item',15:'tab',16:'progress_bar',17:'toolbar',18:'status_bar',
    19:'link',20:'icon',21:'spinner_button'}

RESOLUTIONS = [(1024, 768), (1280, 720), (1366, 768), (1440, 900), (1920, 1080)]

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
    ("find_replace", gen.make_find_replace),
    ("print_dialog", gen.make_print_dialog),
    ("about_dialog", gen.make_about_dialog),
    ("file_properties", gen.make_file_properties),
    ("system_tray", gen.make_system_tray_popup),
    ("form_fill", gen.make_form_fill),
]


def main():
    gen.set_split("all")
    os.makedirs(f"{OUTPUT_DIR}/images", exist_ok=True)
    os.makedirs(f"{OUTPUT_DIR}/labels", exist_ok=True)

    manifest = []
    total_images = 0
    class_counts = Counter()

    print(f"Generating {SAMPLES_PER_SCENE} images per scene type...")
    print(f"Target: {len(SCENE_TYPES)} scenes × {SAMPLES_PER_SCENE} = {len(SCENE_TYPES)*SAMPLES_PER_SCENE} images\n")
    t0 = time.time()

    for scene_name, scene_fn in GENERATORS:
        scene_t0 = time.time()
        scene_count = 0

        for _i in range(SAMPLES_PER_SCENE):
            gen.DESKTOP_SIZE = random.choice(RESOLUTIONS)
            page = scene_fn()
            img = page.image
            if img is None:
                continue

            # Save image
            fname = f"{scene_name}_{total_images:06d}.png"
            fpath = os.path.join(OUTPUT_DIR, "images", fname)
            cv2.imwrite(fpath, img)

            # Save YOLO labels
            h, w = img.shape[:2]
            lbl_path = os.path.join(OUTPUT_DIR, "labels", f"{scene_name}_{total_images:06d}.txt")
            with open(lbl_path, "w") as lf:
                for elem in page.elements:
                    label = gen.yolo_label(elem, w, h)
                    lf.write(label + "\n")
                    class_counts[elem.cls_id] += 1

            manifest.append({
                "file": fname,
                "generator": scene_name,
                "elements": len(page.elements),
                "resolution": f"{w}x{h}",
            })
            total_images += 1
            scene_count += 1

        elapsed = time.time() - scene_t0
        print(f"  {scene_name:<20s} {scene_count:>3d} images  {elapsed:>4.1f}s")

    # Save manifest
    with open(os.path.join(OUTPUT_DIR, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nTotal: {total_images} images in {time.time()-t0:.0f}s")
    print(f"\nClass distribution ({len(class_counts)} classes):")
    print(f"  {'Class':<20s} {'Count':>6s} {'Sufficient?':>10s}")
    print(f"  {'-'*20} {'-'*6} {'-'*10}")
    for cls_id in sorted(class_counts.keys()):
        name = CLASS_NAMES.get(cls_id, f"cls_{cls_id}")
        n = class_counts[cls_id]
        power = "✅ N>=30" if n >= 30 else "⚠️ N<30" if n > 0 else "❌ MISSING"
        print(f"  {name:<20s} {n:>6d} {power:>10s}")


if __name__ == "__main__":
    main()
