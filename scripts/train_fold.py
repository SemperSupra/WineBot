#!/usr/bin/env python3
"""Train YOLO on one fold. Called as subprocess by cv_cross_validate.sh.
Args: fold_dir epochs
Only imports YOLO — no generator imports. Clean PyTorch multiprocessing."""
import csv, json, os, sys, time

os.environ["CUDA_VISIBLE_DEVICES"] = "0"
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from logging_utils import get_logger
from ultralytics import YOLO

logger = get_logger("train_fold")

fold_dir = sys.argv[1]
epochs = int(sys.argv[2])

logger.start(f"Training fold {os.path.basename(fold_dir)}", epochs=epochs, fold_dir=fold_dir)

t0 = time.time()
model = YOLO("yolo26s.pt")
logger.step("load", f"Model loaded in {time.time()-t0:.1f}s, device: {model.device}")

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
    workers=4, deterministic=True, seed=0,
)

best_map50 = 0
csv_path = f"{fold_dir}/yolo/train/results.csv"
if os.path.isfile(csv_path):
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            m50 = float(row.get("metrics/mAP50(B)", 0))
            best_map50 = max(best_map50, m50)

with open(f"{fold_dir}/result.json", "w") as f:
    json.dump({"best_mAP50": best_map50}, f)

logger.complete(f"Best mAP50: {best_map50:.4f}", best_mAP50=best_map50)
print(f"Done. Best mAP50: {best_map50:.4f}", flush=True)
