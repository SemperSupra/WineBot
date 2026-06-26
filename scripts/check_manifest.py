#!/usr/bin/env python3
"""Check manifest structure to understand splits and scene types."""
import json
from collections import Counter

with open("/models/wine-dataset-10k/manifest.json") as f:
    manifest = json.load(f)

print(f"Type: {type(manifest).__name__}")
if isinstance(manifest, dict):
    print(f"Keys: {list(manifest.keys())}")
    print(f"Split: {manifest.get('split')}")
    images = manifest.get("images", [])
elif isinstance(manifest, list):
    images = manifest
    print(f"List of {len(manifest)} items")

print(f"\nTotal image entries: {len(images)}")

# Count splits
splits = Counter()
scenes = Counter()
for entry in images:
    splits[entry.get("split", "unknown")] += 1
    scenes[entry.get("generator", "unknown")] += 1

print(f"\nSplits: {dict(splits)}")
print(f"\nScenes: {dict(scenes)}")
