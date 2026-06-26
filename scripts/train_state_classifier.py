#!/usr/bin/env python3
"""Train a screen state classifier from CLIP embeddings + GT scene labels.

We have 10K frames with known scene types (save_dialog, settings, etc.)
from the GT generator manifest. This trains a lightweight classifier
on CLIP embeddings for ~10ms inference — enabling a live state machine.

Usage:
  docker exec winebot-cv python3 /tmp/train_state_classifier.py

Output:
  - Trained classifier at /models/state_classifier/
  - Accuracy report per scene type
"""
import json, os, pickle, sys, time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, "/scripts")
from clip_embedder import get_clip_embedder

MODEL_DIR = "/models/state_classifier"
MANIFEST = "/models/wine-dataset-10k/manifest.json"
IMAGE_DIRS = {
    "train": "/models/wine-dataset-10k/train/images",
    "val": "/models/wine-dataset-10k/val/images",
    "test": "/models/wine-dataset-10k/test/images",
}

# All 15 scene types
SCENE_TYPES = [
    "save_dialog", "settings", "error_dialog", "notepad",
    "control_panel", "file_manager", "multi_window", "browser",
    "terminal", "context_menu", "wizard", "about_dialog",
    "file_properties", "system_tray", "form_fill",
]
SCENE_TO_IDX = {s: i for i, s in enumerate(SCENE_TYPES)}


def load_manifest(path: str) -> dict:
    """Load manifest and return {filename: {scene_type, split, elements, ocr_texts}}."""
    with open(path) as f:
        manifest = json.load(f)
    entries = {}
    # Handle both list and dict-with-split formats
    images = manifest if isinstance(manifest, list) else manifest.get("images", [])
    for entry in images:
        fname = entry.get("file", "")
        scene = entry.get("generator", "unknown")
        split = entry.get("split", "unknown")
        entries[fname] = {
            "scene": scene,
            "split": split,
            "elements": entry.get("elements", 0),
            "ocr_texts": entry.get("ocr_texts", 0),
        }
    return entries


def extract_clip_embeddings(clip, image_dir: str, filenames: list) -> np.ndarray:
    """Batch-extract CLIP embeddings for a list of filenames."""
    embeddings = []
    valid_files = []
    for fname in filenames:
        path = os.path.join(image_dir, fname)
        img = cv2.imread(path)
        if img is None:
            continue
        emb = clip.embed_image(img)
        embeddings.append(emb)
        valid_files.append(fname)
    return np.array(embeddings, dtype=np.float32), valid_files


def train_classifier(X_train: np.ndarray, y_train: np.ndarray):
    """Train a lightweight classifier on CLIP embeddings.

    Uses sklearn LogisticRegression with balanced class weights.
    Fast to train, ~10ms inference, works well on 512-dim embeddings.
    """
    from sklearn.linear_model import LogisticRegression

    n_classes = len(np.unique(y_train))
    print(f"  Classes in training: {n_classes}")
    print(f"  Training samples: {len(y_train)}")

    clf = LogisticRegression(
        C=1.0,
        max_iter=1000,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )

    t0 = time.time()
    clf.fit(X_train, y_train)
    elapsed = time.time() - t0
    print(f"  Training time: {elapsed:.1f}s")

    return clf


def evaluate(clf, X_test: np.ndarray, y_test: np.ndarray,
             filenames: list, gt_lookup: dict) -> dict:
    """Evaluate classifier and return detailed results."""
    from sklearn.metrics import accuracy_score, confusion_matrix, classification_report

    y_pred = clf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)

    # Per-class accuracy
    by_type = Counter()
    by_type_correct = Counter()
    for true, pred in zip(y_test, y_pred):
        actual = SCENE_TYPES[true] if true < len(SCENE_TYPES) else "unknown"
        predicted = SCENE_TYPES[pred] if pred < len(SCENE_TYPES) else "unknown"
        by_type[actual] += 1
        if true == pred:
            by_type_correct[actual] += 1

    # Confusion matrix
    cm = confusion_matrix(y_test, y_pred)
    labels = [SCENE_TYPES[i] for i in range(min(len(SCENE_TYPES), cm.shape[0]))]

    results = {
        "accuracy": float(acc),
        "samples": len(y_test),
        "per_class": {},
        "confusion": [],
    }

    print(f"\n{'='*60}")
    print(f"  State Classifier Results")
    print(f"  Accuracy: {acc*100:.1f}% ({len(y_test)} samples)")
    print(f"{'='*60}\n")
    print(f"  {'Scene Type':<25s} {'Accuracy':>10s} {'Samples':>8s}")
    print(f"  {'-'*25} {'-'*10} {'-'*8}")

    for scene in sorted(by_type.keys()):
        n = by_type[scene]
        c = by_type_correct.get(scene, 0)
        acc_class = c / n * 100 if n > 0 else 0
        bar = "#" * max(1, int(acc_class / 5))
        print(f"  {scene:<25s} {acc_class:>8.1f}% ({c:>3d}/{n:<3d}) {bar}")
        results["per_class"][scene] = {
            "accuracy": round(acc_class, 1),
            "correct": c,
            "total": n,
        }

    # Top confusions (use only the classes that appear in this eval)
    eval_classes = sorted(set(y_test) | set(y_pred))
    eval_labels = [SCENE_TYPES[i] for i in eval_classes if i < len(SCENE_TYPES)]
    print(f"\n  Top Confusions:")
    confusion_list = []
    for i, ci in enumerate(eval_classes):
        for j, cj in enumerate(eval_classes):
            if i != j and cm[i][j] > 0:
                confusion_list.append((eval_labels[i], eval_labels[j], int(cm[i][j])))
    confusion_list.sort(key=lambda x: -x[2])
    for actual, predicted, count in confusion_list[:8]:
        print(f"    {actual:<20s} → {predicted:<20s} {count:>4d}")
        results["confusion"].append({
            "actual": actual, "predicted": predicted, "count": count,
        })

    return results


def main():
    os.makedirs(MODEL_DIR, exist_ok=True)

    print("Loading CLIP embedder...")
    clip = get_clip_embedder()
    if not clip.available:
        print("ERROR: CLIP not available")
        sys.exit(1)
    print(f"  CLIP dim: {clip.dim}")

    print("Loading manifest...")
    gt = load_manifest(MANIFEST)
    print(f"  Loaded {len(gt)} entries")

    # Manifest only covers test split (system_tray, form_fill).
    # Stratified 70/30 split to preserve class balance.
    from collections import defaultdict
    items_by_scene = defaultdict(list)
    for fname, info in gt.items():
        scene = info.get("scene", "unknown")
        if scene in SCENE_TO_IDX:
            items_by_scene[scene].append((fname, info))

    train_fnames, train_labels = [], []
    test_fnames, test_labels = [], []
    for scene, items in items_by_scene.items():
        items.sort()  # deterministic
        n = len(items)
        n_train = int(n * 0.7)
        for fname, info in items[:n_train]:
            train_fnames.append(fname)
            train_labels.append(SCENE_TO_IDX[scene])
        for fname, info in items[n_train:]:
            test_fnames.append(fname)
            test_labels.append(SCENE_TO_IDX[scene])

    print(f"  Train: {len(train_fnames)} images")
    print(f"  Test:  {len(test_fnames)} images")
    print(f"  Classes: {set(SCENE_TYPES[i] for i in set(train_labels + test_labels))}")

    splits = {"train": (train_fnames, train_labels), "test": (test_fnames, test_labels)}

    # Extract embeddings for train and test sets
    for split_name in ["train", "test"]:
        valid_fnames, valid_labels = splits[split_name]
        print(f"\nExtracting CLIP embeddings for {split_name} ({len(valid_fnames)} images)...")

        # All images are in the test directory (manifest covers test split only)
        image_dir = "/models/wine-dataset-10k/test/images"
        if not os.path.isdir(image_dir):
            print(f"  SKIP: {image_dir} not found")
            continue

        embeddings, loaded_fnames = extract_clip_embeddings(clip, image_dir, valid_fnames)

        # Align labels with loaded files
        label_map = {f: l for f, l in zip(valid_fnames, valid_labels)}
        loaded_labels = np.array([label_map[f] for f in loaded_fnames])

        if split_name == "train":
            X_train, y_train = embeddings, loaded_labels
            train_files = loaded_fnames
            print(f"  Train embeddings: {X_train.shape}")
        else:
            X_test, y_test = embeddings, loaded_labels
            test_files = loaded_fnames
            print(f"  Test embeddings: {X_test.shape}")

    # Train
    print(f"\nTraining classifier...")
    clf = train_classifier(X_train, y_train)

    # Evaluate
    results = evaluate(clf, X_test, y_test, test_files, gt)

    # Save model
    model_path = os.path.join(MODEL_DIR, "state_classifier.pkl")
    with open(model_path, "wb") as f:
        pickle.dump({
            "classifier": clf,
            "scene_types": SCENE_TYPES,
            "clip_dim": clip.dim,
            "train_accuracy": results["accuracy"],
            "train_samples": results["samples"],
            "per_class_accuracy": results["per_class"],
        }, f)
    print(f"\nModel saved: {model_path} ({os.path.getsize(model_path)/1024:.0f} KB)")

    # Save results JSON
    results_path = os.path.join(MODEL_DIR, "eval_results.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved: {results_path}")

    return results


if __name__ == "__main__":
    main()
