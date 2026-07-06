#!/usr/bin/env python3
"""Evaluate CLIP zero-shot screen state classification.

Tests how well CLIP can classify desktop screenshots into scene types
(save_dialog, settings, notepad, error_dialog, etc.) using zero-shot
text prompts. This is the foundation for a live state machine.

Usage:
  docker exec winebot-cv python3 /tmp/test_state_classifier.py

Output:
  Per-scene accuracy and confusion matrix
"""
import json
import os
import sys
from collections import Counter

import cv2
import numpy as np

sys.path.insert(0, "/scripts")
from clip_embedder import get_clip_embedder

# Scene types from our GT dataset (15 types)
SCENE_TYPES = [
    "save_dialog", "settings", "error_dialog", "notepad",
    "control_panel", "file_manager", "multi_window", "browser",
    "terminal", "context_menu", "wizard", "about_dialog",
    "file_properties", "system_tray", "form_fill",
]

# CLIP-friendly descriptions for each scene
SCENE_PROMPTS = [
    "a save dialog with file name and type fields and save cancel buttons",
    "a settings window with tabs checkboxes and configuration options",
    "an error dialog with error message and ok button",
    "a notepad text editor with menu bar and text editing area",
    "a control panel with settings categories and icons",
    "a file manager with file listing toolbar and folder navigation",
    "a desktop with multiple open windows stacked on each other",
    "a web browser with navigation buttons and address bar",
    "a terminal window with command prompt and text output",
    "a context menu with popup options list",
    "a wizard dialog with step indicators and navigation buttons",
    "an about dialog with application name version and copyright",
    "a file properties dialog with metadata tabs and attributes",
    "a system tray area with notification icons and clock",
    "a form fill dialog with input fields dropdowns and submit button",
]


def load_ground_truth(split: str = "test") -> dict:
    """Load scene type labels from dataset manifest.

    Returns: {filename: scene_type}
    """
    manifest_path = "/models/wine-dataset-10k/manifest.json"
    gt = {}
    with open(manifest_path) as f:
        data = json.load(f)

    # Handle both single-split and multi-split manifests
    images = data if isinstance(data, list) else data.get("images", [])

    # Filter by split if manifest has split info
    data.get("split", split) if isinstance(data, dict) else split
    if isinstance(data, dict) and data.get("split") != split:
        # manifest might cover different split, but still use all available
        # since we can filter by image directory instead
        pass

    for entry in images:
        if isinstance(entry, dict):
            fname = entry.get("file", "")
            scene = entry.get("generator", "unknown")
            gt[fname] = scene
    return gt


def main():
    clip = get_clip_embedder()
    if not clip.available:
        print("ERROR: CLIP not available")
        sys.exit(1)

    # Use test split
    test_dir = "/models/wine-dataset-10k/test/images"
    if not os.path.isdir(test_dir):
        test_dir = "/models/wine-dataset-10k/val/images"

    # Load ground truth from manifest
    gt = load_ground_truth("test")

    # Get files that exist in the test directory AND have GT labels
    all_files = sorted([f for f in os.listdir(test_dir)
                        if f.endswith((".png", ".jpg"))])
    frame_files = [f for f in all_files if f in gt][:500]
    print(f"Loaded GT for {len(gt)} images, {len(frame_files)} in test dir")

    print(f"Testing CLIP zero-shot state classification on {len(frame_files)} frames\n")

    correct = 0
    total = 0
    by_type = Counter()
    by_type_correct = Counter()
    confusion = {}  # (actual, predicted) → count
    all_probs = []

    for i, fname in enumerate(frame_files):
        actual = gt.get(fname, "unknown")
        img = cv2.imread(os.path.join(test_dir, fname))
        if img is None:
            continue

        # Classify via CLIP zero-shot
        probs = clip.classify(img, SCENE_PROMPTS)

        # Find predicted scene (highest probability)
        predicted_prompt = max(probs, key=probs.get)
        # Map prompt back to scene type
        pred_idx = SCENE_PROMPTS.index(predicted_prompt)
        predicted = SCENE_TYPES[pred_idx]

        by_type[actual] += 1
        if actual == predicted:
            correct += 1
            by_type_correct[actual] += 1
        else:
            key = (actual, predicted)
            confusion[key] = confusion.get(key, 0) + 1

        total += 1
        all_probs.append(probs)

        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(frame_files)} processed...")

    # Results
    print(f"\n{'='*60}")
    print("  CLIP Zero-Shot State Classification Results")
    print(f"  Overall Accuracy: {correct}/{total} = {correct/total*100:.1f}%")
    print(f"{'='*60}\n")

    print(f"  {'Scene Type':<25s} {'Accuracy':>10s} {'Samples':>8s}")
    print(f"  {'-'*25} {'-'*10} {'-'*8}")
    for scene in sorted(by_type.keys()):
        n = by_type[scene]
        c = by_type_correct.get(scene, 0)
        acc = c / n * 100 if n > 0 else 0
        bar = "#" * max(1, int(acc / 5))
        print(f"  {scene:<25s} {acc:>8.1f}% ({c:>3d}/{n:<3d}) {bar}")

    print()
    if confusion:
        print("  Top Confusions:")
        print(f"  {'Actual':<20s} → {'Predicted':<20s} {'Count':>6s}")
        print(f"  {'-'*20}   {'-'*20} {'-'*6}")
        for (actual, predicted), count in sorted(
                confusion.items(), key=lambda x: -x[1])[:10]:
            print(f"  {actual:<20s} → {predicted:<20s} {count:>6d}")

    print("\n  Aggregate probabilities across all scenes:")
    # Average probability of correct class
    avg_correct_prob = []
    for i, fname in enumerate(frame_files):
        actual = gt.get(fname, "unknown")
        if actual in SCENE_TYPES:
            prompt_idx = SCENE_TYPES.index(actual)
            avg_correct_prob.append(all_probs[i][SCENE_PROMPTS[prompt_idx]])
    if avg_correct_prob:
        print(f"  Mean confidence in correct class: {np.mean(avg_correct_prob)*100:.1f}%")


if __name__ == "__main__":
    main()
