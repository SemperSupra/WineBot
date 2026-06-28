#!/usr/bin/env python3
"""Generate data for one fold. Args: fold fold_dir n_per_scene n_train scene1 scene2 ... (all scenes).
First n_train scenes are training, rest are validation. No PyTorch imports."""
import importlib.util
import os
import random
import sys
import time

import cv2

sys.path.insert(0, os.path.dirname(__file__))
from logging_utils import get_logger

logger = get_logger("gen_fold")

spec = importlib.util.spec_from_file_location("gt", "/scripts/winebot-gt-generator.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

fold = int(sys.argv[1])
fold_dir = sys.argv[2]
images_per_scene = int(sys.argv[3])
n_train = int(sys.argv[4])

# Ensure directories exist
for sub in ["train/images", "train/labels", "val/images", "val/labels"]:
    os.makedirs(os.path.join(fold_dir, sub), exist_ok=True)

all_scenes = sys.argv[5:]
train_scenes = set(all_scenes[:n_train])
val_scenes = set(all_scenes[n_train:])

rng = random.Random(42 + fold)
resolutions = [(1280, 720), (1366, 768)]
total = 0
t0 = time.time()

for scene_name, scene_fn in gen.GENERATORS:
    if scene_name not in train_scenes and scene_name not in val_scenes:
        continue
    target = "val" if scene_name in val_scenes else "train"
    for _i in range(images_per_scene):
        gen.DESKTOP_SIZE = rng.choice(resolutions)
        try:
            page = scene_fn()
        except Exception:
            continue
        img = page.image
        if img is None:
            continue
        fname = f"{scene_name}_{total:06d}.png"
        cv2.imwrite(os.path.join(fold_dir, target, "images", fname), img)
        h, w = img.shape[:2]
        with open(os.path.join(fold_dir, target, "labels",
                                fname.replace(".png", ".txt")), "w") as lf:
            for elem in page.elements:
                lf.write(gen.yolo_label(elem, w, h) + "\n")
        total += 1

logger.complete(f"Generated {total} images", total=total, elapsed_s=round(time.time()-t0, 1))
print(f"Generated {total} images in {time.time()-t0:.0f}s", flush=True)
