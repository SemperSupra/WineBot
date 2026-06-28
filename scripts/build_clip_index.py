#!/usr/bin/env python3
"""Build CLIP embedding index on all 10K dataset splits.

Usage: python3 build_clip_index.py [--dataset /models/wine-dataset-10k] [--output /models/frame_index]
"""

import argparse
import os
import sys
import time

import cv2


def build_index_for_split(split_name: str, frames_dir: str, index_dir: str,
                          clip, max_frames: int = 10000):
    """Build and save a CLIP embedding index for one dataset split."""
    from clip_index import FrameIndex

    print(f"\n{'='*60}")
    print(f"Building index for {split_name} ({frames_dir})")
    print(f"{'='*60}")

    frame_files = sorted([
        f for f in os.listdir(frames_dir)
        if f.endswith(('.png', '.PNG'))
    ])[:max_frames]

    if not frame_files:
        print(f"  WARNING: No frames in {frames_dir}")
        return None

    print(f"  Frames: {len(frame_files)}")

    split_index_dir = os.path.join(index_dir, split_name)
    idx = FrameIndex(split_index_dir)
    t0 = time.time()
    batch_size = 32

    for i in range(0, len(frame_files), batch_size):
        batch = frame_files[i:i + batch_size]
        images = []
        valid_fnames = []
        for fname in batch:
            path = os.path.join(frames_dir, fname)
            img = cv2.imread(path)
            if img is not None:
                images.append(img)
                valid_fnames.append(fname)

        if images:
            embeddings = clip.embed_batch(images)
            metadatas = [{"filename": fn, "split": split_name}
                         for fn in valid_fnames]
            idx.add_batch(valid_fnames, embeddings, metadatas)

        if (i + batch_size) % 1000 == 0 or i + batch_size >= len(frame_files):
            elapsed = time.time() - t0
            fps = len(valid_fnames) / max(1e-6, (time.time() - t0))  # doesn't matter here
            processed = min(i + batch_size, len(frame_files))
            print(f"  [{processed:6d}/{len(frame_files)}] "
                  f"{elapsed:.1f}s")

    idx.save()

    elapsed = time.time() - t0
    fps = len(frame_files) / elapsed if elapsed > 0 else 0
    print(f"  Done: {len(frame_files)} frames in {elapsed:.1f}s ({fps:.0f} fps)")
    print(f"  Saved: {split_index_dir}")
    return idx


def main():
    parser = argparse.ArgumentParser(description="Build CLIP embedding index")
    parser.add_argument("--dataset", default="/models/wine-dataset-10k",
                        help="Dataset root directory")
    parser.add_argument("--output", default="/models/frame_index",
                        help="Output index directory")
    parser.add_argument("--max-frames", type=int, default=10000,
                        help="Max frames per split")
    args = parser.parse_args()

    sys.path.insert(0, "/scripts")
    os.chdir("/scripts")

    from clip_embedder import get_clip_embedder
    clip = get_clip_embedder()
    if not clip.available:
        print("ERROR: No CLIP backend available", file=sys.stderr)
        sys.exit(1)

    print(f"CLIP: {clip.name}, dim={clip.dim}, GPU={clip.uses_gpu}")

    splits = {
        "train": os.path.join(args.dataset, "train", "images"),
        "val": os.path.join(args.dataset, "val", "images"),
        "test": os.path.join(args.dataset, "test", "images"),
    }

    os.makedirs(args.output, exist_ok=True)

    for split_name, frames_dir in splits.items():
        if os.path.isdir(frames_dir):
            build_index_for_split(split_name, frames_dir, args.output,
                                 clip, args.max_frames)
        else:
            print(f"  SKIP: {frames_dir} not found")

    print("\nDone!")


if __name__ == "__main__":
    main()
