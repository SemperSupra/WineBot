#!/usr/bin/env python3
"""K-fold cross-validation — runs data generation and training in subprocesses.

Each fold is fully isolated: data generation + training run as separate
subprocess calls, avoiding any import conflicts between the GT generator
and PyTorch's multiprocessing.
"""
import argparse, csv, json, os, subprocess, sys, time

import numpy as np

SCENES = [
    "save_dialog", "settings", "error_dialog", "notepad", "control_panel",
    "file_manager", "multi_window", "browser", "terminal", "context_menu",
    "wizard", "find_replace", "print_dialog", "about_dialog", "file_properties",
    "system_tray", "form_fill", "login", "toast", "data_table", "drag_drop",
    "loading",
]

CLASSES = [
    "title_bar", "title_text", "button", "close_button", "text_field",
    "dropdown", "checkbox", "radio", "menu_bar", "menu_item", "taskbar",
    "dialog", "text_area", "scrollbar", "list_item", "tab", "progress_bar",
    "toolbar", "status_bar", "link", "icon", "spinner_button",
]

TRAIN_SCRIPT = r"""
import json, os, sys, csv
import numpy as np
import torch

# Make sure CUDA is visible
os.environ['CUDA_VISIBLE_DEVICES'] = '0'

from ultralytics import YOLO

fold_dir = sys.argv[1]
epochs = int(sys.argv[2])

model = YOLO("yolo26s.pt")
print(f"[fold] Model loaded, device: {model.device}")

results = model.train(
    data=f"{fold_dir}/data.yaml",
    epochs=epochs, imgsz=1280, batch=4, device=0,
    lr0=0.001, freeze=0, patience=5,
    pretrained=True, augment=True,
    mosaic=1.0, close_mosaic=10, mixup=0.1,
    fliplr=0.5, scale=0.5, dropout=0.05, cos_lr=True,
    hsv_h=0.015, hsv_s=0.4, hsv_v=0.4,
    translate=0.1, save=True, save_period=30,
    project=f"{fold_dir}/yolo", name="train", exist_ok=True,
    workers=8, deterministic=True, seed=0,
)

best_map50 = 0
csv_path = f"{fold_dir}/yolo/train/results.csv"
if os.path.isfile(csv_path):
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            m50 = float(row.get("metrics/mAP50(B)", 0))
            best_map50 = max(best_map50, m50)

result = {"best_mAP50": best_map50, "model_path": f"{fold_dir}/yolo/train/weights/best.pt"}
json.dump(result, open(f"{fold_dir}/fold_result.json", "w"))
print(f"[fold] Training complete. Best mAP50: {best_map50:.4f}")
"""


def generate_fold_data(fold_dir: str, train_scenes: list, val_scenes: list,
                       images_per_scene: int, fold_seed: int) -> int:
    """Generate YOLO-format data for one fold by writing a temp generator script."""
    # Build a self-contained generation script
    gen_code = f"""#!/usr/bin/env python3
import cv2, os, random, sys
sys.path.insert(0, "/scripts")
import importlib.util
spec = importlib.util.spec_from_file_location("winebot_gt", "/scripts/winebot-gt-generator.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

rng = random.Random({fold_seed})
resolutions = [(1280, 720), (1366, 768), (1920, 1080)]
train_scenes = {train_scenes}
val_scenes = {val_scenes}
total = 0

os.makedirs("{fold_dir}/train/images", exist_ok=True)
os.makedirs("{fold_dir}/train/labels", exist_ok=True)
os.makedirs("{fold_dir}/val/images", exist_ok=True)
os.makedirs("{fold_dir}/val/labels", exist_ok=True)

# Freeze resolution so scene fns see it
gen.DESKTOP_SIZE = (1280, 720)

for scene_name, scene_fn in gen.GENERATORS:
    is_val = scene_name in val_scenes
    is_train = scene_name in train_scenes
    if not is_val and not is_train:
        continue
    target = "val" if is_val else "train"
    for i in range({images_per_scene}):
        gen.DESKTOP_SIZE = rng.choice(resolutions)
        try:
            page = scene_fn()
        except Exception as e:
            print(f"  SKIP {{scene_name}}_{{i}}: {{e}}", file=sys.stderr)
            continue
        img = page.image
        if img is None:
            continue
        fname = f"{{scene_name}}_{{total:06d}}.png"
        cv2.imwrite(os.path.join("{fold_dir}", target, "images", fname), img)
        h, w = img.shape[:2]
        with open(os.path.join("{fold_dir}", target, "labels", fname.replace(".png", ".txt")), "w") as lf:
            for elem in page.elements:
                lf.write(gen.yolo_label(elem, w, h) + "\\n")
        total += 1

print(f"Generated {{total}} images")
"""
    gen_path = f"{fold_dir}/_gen.py"
    os.makedirs(fold_dir, exist_ok=True)
    with open(gen_path, "w") as f:
        f.write(gen_code)

    result = subprocess.run(
        ["python3", gen_path],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        print(f"  [ERROR] Generation failed:\n{result.stderr}", file=sys.stderr)
        raise RuntimeError(f"Data generation failed for fold")

    # Parse total from output
    for line in result.stdout.strip().split("\n"):
        if line.startswith("Generated"):
            return int(line.split()[1])
    return 0


def write_data_yaml(fold_dir: str):
    with open(os.path.join(fold_dir, "data.yaml"), "w") as f:
        f.write(f"path: {fold_dir}\n")
        f.write("train: train/images\n")
        f.write("val: val/images\n")
        f.write(f"nc: {len(CLASSES)}\n")
        f.write("names:\n")
        for i, name in enumerate(CLASSES):
            f.write(f"  {i}: {name}\n")


def train_fold(fold_dir: str, epochs: int) -> dict:
    """Train on one fold by running a subprocess with a clean Python environment."""
    # Write the training script
    script_path = f"{fold_dir}/_train.py"
    with open(script_path, "w") as f:
        f.write(TRAIN_SCRIPT)

    result = subprocess.run(
        ["python3", script_path, fold_dir, str(epochs)],
        capture_output=True, text=True, timeout=7200,  # 2h per fold
    )

    # Print output
    for line in result.stdout.strip().split("\n"):
        if "[fold]" in line:
            print(f"    {line.strip()}")

    if result.returncode != 0:
        stderr_lines = result.stderr.strip().split("\n")[-10:]
        print(f"    [ERROR] Training failed:", file=sys.stderr)
        for l in stderr_lines:
            print(f"      {l}", file=sys.stderr)
        return {"best_mAP50": 0, "model_path": ""}

    # Read result
    result_path = f"{fold_dir}/fold_result.json"
    if os.path.isfile(result_path):
        with open(result_path) as f:
            return json.load(f)
    return {"best_mAP50": 0, "model_path": ""}


def main():
    parser = argparse.ArgumentParser(description="Cross-validation (subprocess-based)")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--images-per-fold", type=int, default=200)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--output", default="/models/cross-validation")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  K-FOLD CROSS-VALIDATION (subprocess isolation)")
    print(f"  Folds: {args.folds}")
    print(f"  Images/fold/scene: {args.images_per_fold}")
    print(f"  Epochs per fold: {args.epochs}")
    print(f"  Scenes: {len(SCENES)}")
    print(f"{'='*60}\n")

    n_val = max(1, len(SCENES) // args.folds)
    fold_results = []

    for fold in range(args.folds):
        print(f"\n{'='*60}")
        print(f"  FOLD {fold + 1}/{args.folds}")
        print(f"{'='*60}")

        val_scenes = list(SCENES[fold * n_val:(fold + 1) * n_val])
        train_scenes = [s for s in SCENES if s not in val_scenes]
        fold_dir = os.path.join(args.output, f"fold-{fold}")

        print(f"  Train: {len(train_scenes)} scenes")
        print(f"  Val:   {len(val_scenes)} scenes — {val_scenes}")
        sys.stdout.flush()

        # Phase 1: Generate data
        t0 = time.time()
        print(f"  [1/2] Generating data...")
        sys.stdout.flush()
        total = generate_fold_data(fold_dir, train_scenes, val_scenes,
                                   args.images_per_fold, fold_seed=42 + fold)
        print(f"  [1/2] {total} images in {time.time()-t0:.0f}s")
        sys.stdout.flush()

        # Write data.yaml
        write_data_yaml(fold_dir)

        # Phase 2: Train
        t0 = time.time()
        print(f"  [2/2] Training ({args.epochs} epochs)...")
        sys.stdout.flush()
        result = train_fold(fold_dir, args.epochs)
        train_time = time.time() - t0

        result.update({
            "fold": fold,
            "val_scenes": val_scenes,
            "train_scenes": train_scenes,
            "total_images": total,
            "train_time_s": round(train_time, 1),
        })
        fold_results.append(result)
        print(f"  Fold {fold + 1}: mAP50={result['best_mAP50']:.4f} "
              f"({train_time:.0f}s)")
        sys.stdout.flush()

    # Summary
    print(f"\n{'='*60}")
    print(f"  CROSS-VALIDATION RESULTS")
    print(f"{'='*60}")
    map50s = [r["best_mAP50"] for r in fold_results]
    print(f"  Mean mAP50: {np.mean(map50s):.4f} ± {np.std(map50s):.4f}")
    print(f"  Per fold:")
    for r in fold_results:
        print(f"    Fold {r['fold']}: mAP50={r['best_mAP50']:.4f} "
              f"(val: {r['val_scenes']})")

    with open(os.path.join(args.output, "results.json"), "w") as f:
        json.dump({
            "n_folds": args.folds,
            "images_per_fold": args.images_per_fold,
            "epochs": args.epochs,
            "mean_mAP50": round(float(np.mean(map50s)), 4),
            "std_mAP50": round(float(np.std(map50s)), 4),
            "per_fold": fold_results,
        }, f, indent=2)
    print(f"\nResults: {os.path.join(args.output, 'results.json')}")


if __name__ == "__main__":
    main()
