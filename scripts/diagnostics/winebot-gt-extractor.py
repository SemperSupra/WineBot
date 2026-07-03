#!/usr/bin/env python3
"""Extract ground truth labels from WineBot session recordings.

Takes watcher.jsonl (per-frame CV analysis) + interaction log (API commands
sent to WineBot) and produces YOLO-format labeled screenshots. Because WineBot
knows what it typed, what it launched, and what windows appeared, we can
auto-label real Wine desktop screenshots — zero manual annotation.

Usage:
  python3 winebot-gt-extractor.py --session /artifacts/sessions/session-*.dir \
    --output /models/wine-dataset-real/
"""

import argparse
import json
import os
import sys


def extract_windows_from_watcher(watcher_path: str) -> dict:
    """Parse watcher.jsonl to get per-frame window inventory and detection data."""
    frames = {}
    if not os.path.exists(watcher_path):
        return frames

    with open(watcher_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("event") != "snapshot":
                continue

            idx = entry.get("index", 0)
            frames[idx] = {
                "frame_path": entry.get("frame_path", ""),
                "windows": entry.get("windows", []),
                "interesting_windows": entry.get("interesting_windows", []),
                "elements": entry.get("elements", {}),
                "pixels_changed": entry.get("pixels_changed", 0),
                "timestamp_utc": entry.get("timestamp_utc", ""),
            }
    return frames


def extract_commands_from_interaction_log(log_path: str) -> list:
    """Parse interaction log for API commands that inform ground truth.

    Expected format: one JSON object per line with 'command', 'timestamp',
    and relevant metadata (window_title, text_typed, element_clicked, etc.)
    """
    commands = []
    if not os.path.exists(log_path):
        return commands

    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                cmd = json.loads(line)
            except json.JSONDecodeError:
                continue
            commands.append(cmd)
    return commands


def match_commands_to_frames(commands: list, frames: dict) -> dict:
    """Correlate interaction commands to watcher frames based on timestamps."""
    annotated = {}

    for cmd in commands:
        cmd_ts = cmd.get("timestamp_epoch_ms", 0)
        cmd.get("command", "")

        # Find the frame closest to this command
        best_frame = None
        best_delta = float("inf")
        for idx, frame in frames.items():
            int(frame.get("timestamp_utc", "2000").replace("-", "")
                            .replace("T", "").replace(":", "").replace("Z", "")[:14] or 0)
            # Use epoch ms if available
            frame_epoch = frame.get("timestamp_epoch_ms", 0)
            if frame_epoch:
                delta = abs(frame_epoch - cmd_ts)
                if delta < best_delta:
                    best_delta = delta
                    best_frame = (idx, frame)

        if best_frame and best_delta < 5000:  # Within 5 seconds
            idx, frame = best_frame
            if idx not in annotated:
                annotated[idx] = {"frame": frame, "commands": []}
            annotated[idx]["commands"].append(cmd)

    return annotated


def commands_to_elements(commands: list, img_w: int = 1280, img_h: int = 720) -> list:
    """Convert interaction commands to approximate UI element bounding boxes.

    WineBot knows command semantics:
    - /apps/run with path="notepad.exe" → Notepad window opened
    - /input/key "text" → text was typed into the active field
    - /input/mouse/click at (x,y) → click happened at coordinates
    - /screenshot → screenshot captured

    Returns list of YOLO-format annotation strings.
    """
    elements = []

    for cmd in commands:
        cmd_type = cmd.get("command", "")

        if cmd_type == "apps/run":
            path = cmd.get("path", "")
            if "notepad" in path.lower():
                # Notepad window: title bar at top, menu, text area
                elements.append("0 0.5 0.06 1.0 0.04")   # title_bar (approx full width)
                elements.append("12 0.5 0.55 0.96 0.85")  # text_area

        elif cmd_type == "input/key":
            text = cmd.get("text", "")
            if text and "notepad" in str(cmd.get("source", "")):
                # Text was typed into Notepad — those characters exist on screen
                pass  # OCR ground truth, not bounding box

        elif cmd_type == "input/mouse/click":
            x, y = cmd.get("x", 0), cmd.get("y", 0)
            # Click at known coordinates
            elements.append(f"2 {x/img_w:.6f} {y/img_h:.6f} 0.005 0.005")

    return elements


def generate_yolo_annotations(annotated_frames: dict, output_dir: str):
    """Write YOLO-format label files alongside frame images."""
    os.makedirs(output_dir, exist_ok=True)
    img_dir = os.path.join(output_dir, "images")
    lbl_dir = os.path.join(output_dir, "labels")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(lbl_dir, exist_ok=True)

    for idx, data in annotated_frames.items():
        frame = data["frame"]
        commands = data["commands"]
        frame_path = frame.get("frame_path", "")
        if not frame_path or not os.path.exists(frame_path):
            continue

        # Copy frame image
        img_name = f"real_{idx:06d}.png"
        import shutil
        shutil.copy2(frame_path, os.path.join(img_dir, img_name))

        # Get elements from watcher
        elements_data = frame.get("elements", {})
        ui_elements = elements_data.get("element_detail", [])

        # Get command-derived annotations
        h, w = 720, 1280  # default; should read from image
        try:
            import cv2
            img = cv2.imread(frame_path)
            if img is not None:
                h, w = img.shape[:2]
        except ImportError:
            pass

        # Write labels
        lbl_path = os.path.join(lbl_dir, f"real_{idx:06d}.txt")
        with open(lbl_path, "w") as f:
            # Command-derived annotations
            cmd_elements = commands_to_elements(commands, w, h)
            for e in cmd_elements:
                f.write(e + "\n")

            # Watcher-detected elements (lower confidence — use as proposals)
            for elem in ui_elements:
                bbox = elem.get("bbox", [0, 0, 0, 0])
                etype = elem.get("type", "unknown")
                # Map watcher types to our class IDs
                cls_map = {
                    "title_bar": 0, "title_text": 1, "button": 2,
                    "close_button": 3, "text_field": 4, "dropdown": 5,
                    "checkbox": 6, "radio": 7, "menu_bar": 8, "menu_item": 9,
                    "taskbar": 10, "dialog": 11, "text_area": 12,
                    "scrollbar": 13, "list_item": 14, "tab": 15,
                    "progress_bar": 16, "toolbar": 17, "status_bar": 18,
                    "link": 19, "icon": 20,
                }
                cls_id = cls_map.get(etype, 20)
                # Only include if we trust the detection (confidence > threshold)
                # For watcher output, conf is typically 0.5 for contour, varies for YOLO
                if etype in ("taskbar", "title_bar", "button", "text_area",
                             "dialog", "menu_bar"):
                    x, y_c, bw, bh = bbox
                    cx = (x + bw / 2) / w
                    cy = (y_c + bh / 2) / h
                    nw = bw / w
                    nh = bh / h
                    f.write(f"{cls_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}\n")


def main():
    parser = argparse.ArgumentParser(
        description="WineBot Ground Truth Extractor — auto-label real desktop screenshots"
    )
    parser.add_argument("--session", help="Path to session directory")
    parser.add_argument("--watcher", help="Path to watcher.jsonl")
    parser.add_argument("--interaction-log", help="Path to interaction log JSONL")
    parser.add_argument("--output", help="Output directory for labeled dataset")
    args = parser.parse_args()

    if args.session:
        cv_dir = os.path.join(args.session, "analysis", "cv")
        watcher_path = os.path.join(cv_dir, "watcher.jsonl")
    elif args.watcher:
        watcher_path = args.watcher
    else:
        print("ERROR: --session or --watcher required", file=sys.stderr)
        sys.exit(1)

    output = args.output or "winebot-gt-extracted"

    print(f"Extracting ground truth from: {watcher_path}")
    frames = extract_windows_from_watcher(watcher_path)
    print(f"  Found {len(frames)} frames with watcher data")

    if args.interaction_log:
        commands = extract_commands_from_interaction_log(args.interaction_log)
        print(f"  Found {len(commands)} interaction commands")
        annotated = match_commands_to_frames(commands, frames)
        print(f"  Matched {len(annotated)} frames to commands")
        generate_yolo_annotations(annotated, output)
    else:
        # Just use watcher elements as pseudo-ground-truth
        annotated = {idx: {"frame": frame, "commands": []}
                     for idx, frame in frames.items()}
        generate_yolo_annotations(annotated, output)

    print(f"Output: {output}/images/ + {output}/labels/")


if __name__ == "__main__":
    main()
