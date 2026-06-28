#!/usr/bin/env python3
"""Generate cross-resolution benchmark test images and run evaluation."""
import json
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from benchmark_dataset import GENERATORS

# Generate test images
test_dir = "/tmp/bench_xres"
os.makedirs(test_dir, exist_ok=True)
manifest = {"dataset": "winebot-cross-res", "images": []}
resolutions = [(1024, 768), (1280, 720), (1366, 768), (1440, 900), (1920, 1080)]

for name, gen_fn in GENERATORS.items():
    for res in resolutions:
        img, gt = gen_fn()
        img = cv2.resize(img, res)
        sx, sy = res[0] / 1280.0, res[1] / 720.0
        for e in gt.get("expected_elements", []):
            bx, by, bw, bh = e["bbox"]
            e["bbox"] = [int(bx * sx), int(by * sy), int(bw * sx), int(bh * sy)]
        img_name = f"{name}_{res[0]}x{res[1]}.png"
        cv2.imwrite(os.path.join(test_dir, img_name), img)
        manifest["images"].append({
            "name": f"{name}_{res[0]}x{res[1]}",
            "path": os.path.join(test_dir, img_name),
            "size": list(res[::-1]),
            "ground_truth": gt,
        })

with open(os.path.join(test_dir, "manifest.json"), "w") as f:
    json.dump(manifest, f, indent=2)

print(f"Generated {len(manifest['images'])} images at {len(resolutions)} resolutions")


# Evaluate model at each resolution
def evaluate_resolution(model_path, test_dir, resolution):
    """Run detection at a given resolution, compute accuracy metrics."""
    from ultralytics import YOLO

    model = YOLO(model_path)
    model.to("cuda")

    # Find images at this resolution
    images = sorted([
        f for f in os.listdir(test_dir)
        if f.endswith(".png") and f"_{resolution[0]}x{resolution[1]}" in f
    ])

    times, elems, scores = [], [], []
    for img_name in images:
        img = cv2.imread(os.path.join(test_dir, img_name))
        t0 = time.time()
        results = model(img, verbose=False, conf=0.35, imgsz=min(img.shape[:2]))
        elapsed = (time.time() - t0) * 1000
        times.append(elapsed)
        boxes = results[0].boxes
        n = len(boxes) if boxes else 0
        elems.append(n)
        if boxes and n > 0:
            scores.append(float(boxes.conf.mean()))

    return {
        "resolution": f"{resolution[0]}x{resolution[1]}",
        "images": len(images),
        "mean_ms": float(np.mean(times)) if times else 0,
        "mean_elements": float(np.mean(elems)) if elems else 0,
        "mean_confidence": float(np.mean(scores)) if scores else 0,
    }


if __name__ == "__main__":
    model_path = sys.argv[1] if len(sys.argv) > 1 else "/models/yolo/wine-finetuned-v2.pt"
    print(f"\nCross-resolution evaluation: {model_path}")
    results = []
    for res in resolutions:
        r = evaluate_resolution(model_path, test_dir, res)
        results.append(r)
        print(f"  {r['resolution']:>11}: {r['mean_ms']:5.0f}ms  "
              f"{r['mean_elements']:4.1f} elem  conf={r['mean_confidence']:.3f}")

    baseline = results[1]  # 1280x720 is baseline
    for r in results:
        if r == baseline:
            continue
        ratio = r["mean_elements"] / max(baseline["mean_elements"], 1)
        print(f"  {r['resolution']} vs baseline: elem ratio={ratio:.2f}")
