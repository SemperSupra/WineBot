#!/usr/bin/env python3
"""Fix out-of-bounds coordinates in existing YOLO label files.

The GT generator's yolo_label() function didn't clamp normalized
coordinates to [0, 1], so elements extending past image edges
produced invalid labels like [1.05, 1.04, 1.02].

This script reads all existing .txt files, clamps values to [0, 1],
and rewrites them in place. Also prunes zero-area boxes.
"""
import os
import sys

DATASET_DIRS = [
    "/models/wine-dataset-10k/train/labels",
    "/models/wine-dataset-10k/val/labels",
    "/models/wine-dataset-10k/test/labels",
]


def fix_label_file(path: str) -> tuple:
    """Fix a single label file. Returns (fixed_count, removed_count)."""
    fixed = 0
    removed = 0
    new_lines = []

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 5:
                continue

            try:
                cls_id = parts[0]
                vals = [float(v) for v in parts[1:5]]
            except ValueError:
                removed += 1
                continue

            # Check if any value is out of bounds
            orig = vals.copy()
            vals = [max(0.0, min(1.0, v)) for v in vals]

            # Prune zero-area boxes (after clamping)
            if vals[2] < 0.001 or vals[3] < 0.001:
                removed += 1
                continue

            if vals != orig:
                fixed += 1

            new_lines.append(f"{cls_id} {vals[0]:.6f} {vals[1]:.6f} {vals[2]:.6f} {vals[3]:.6f}")

    if fixed > 0 or removed > 0:
        with open(path, "w") as f:
            for line in new_lines:
                f.write(line + "\n")

    return fixed, removed


def main():
    total_fixed = 0
    total_removed = 0
    total_checked = 0

    for label_dir in DATASET_DIRS:
        if not os.path.isdir(label_dir):
            print(f"  SKIP: {label_dir} not found")
            continue

        label_files = sorted([f for f in os.listdir(label_dir) if f.endswith(".txt")])
        print(f"Processing {len(label_files)} files in {label_dir}...")

        for fname in label_files:
            fpath = os.path.join(label_dir, fname)
            fixed, removed = fix_label_file(fpath)
            if fixed > 0 or removed > 0:
                total_fixed += fixed
                total_removed += removed
                total_checked += 1

    print(f"\nFixed {total_fixed} coordinates, removed {total_removed} zero-area boxes")
    print(f"Modified {total_checked} label files")


if __name__ == "__main__":
    main()
