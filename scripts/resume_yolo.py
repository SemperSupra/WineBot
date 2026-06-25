#!/usr/bin/env python3
"""Resume YOLO26-N training from last checkpoint."""
from ultralytics import YOLO

model = YOLO("/models/yolo/wine-yolo26n/weights/last.pt")
model.train(resume=True)
