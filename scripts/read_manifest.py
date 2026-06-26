#!/usr/bin/env python3
"""Read dataset manifest and show scene type distribution."""
import json

with open("/models/wine-dataset-10k/manifest.json") as f:
    manifest = json.load(f)

print(f"Total entries: {len(manifest)}")
print(f"Keys: {list(manifest.keys())[:10]}")
print(json.dumps(manifest, indent=2)[:3000])
