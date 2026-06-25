#!/usr/bin/env python3
"""Generate Florence-2 caption training pairs from Wine GT dataset.

Reads the 10K YOLO-format dataset and generates structured caption pairs
(image → structured text description) for fine-tuning Florence-2.

Output: JSONL with lines:
  {"image_path": "/path/to/image.png", "caption": "A save dialog..."}

Usage:
  python3 generate_caption_training_data.py \
    --dataset /models/wine-dataset-10k \
    --output /models/florence2-training/captions.jsonl \
    --split train --max-samples 5000
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

# Label names from data.yaml
CLASS_NAMES = {
    0: "title_bar", 1: "title_text", 2: "button", 3: "close_button",
    4: "text_field", 5: "dropdown", 6: "checkbox", 7: "radio",
    8: "menu_bar", 9: "menu_item", 10: "taskbar", 11: "dialog",
    12: "text_area", 13: "scrollbar", 14: "list_item", 15: "tab",
    16: "progress_bar", 17: "toolbar", 18: "status_bar", 19: "link",
    20: "icon", 21: "spinner_button",
}

# Caption templates per class (for generating natural language descriptions)
CLASS_DESCRIPTORS = {
    0: "title bar",
    1: "title text",
    2: "button",
    3: "close button",
    4: "text input field",
    5: "dropdown menu",
    6: "checkbox",
    7: "radio button",
    8: "menu bar",
    9: "menu item",
    10: "taskbar",
    11: "dialog box",
    12: "text area",
    13: "scrollbar",
    14: "list item",
    15: "tab",
    16: "progress bar",
    17: "toolbar",
    18: "status bar",
    19: "link",
    20: "icon",
    21: "spinner button",
}

# Scene type patterns for richer captions
SCENE_PATTERNS = {
    "save_dialog": "A Save dialog titled '{}' with fields for file name and type selection.",
    "settings": "A Settings window titled '{}' with configuration options organized in tabs.",
    "error_dialog": "An Error dialog titled '{}' with a message and action buttons.",
    "notepad": "A Notepad text editor window titled '{}' with a menu bar and text area.",
    "control_panel": "A Control Panel window titled '{}' with settings categories.",
    "file_manager": "A File Manager window titled '{}' showing a file listing with a toolbar.",
    "browser": "A Browser window titled '{}' with navigation controls and web content area.",
    "terminal": "A Terminal window titled '{}' with a command prompt and text output area.",
    "context_menu": "A Context menu with options for the selected element.",
    "wizard": "A Wizard dialog titled '{}' with step-by-step configuration pages.",
    "multi_window": "Multiple windows: {}.",
    "about_dialog": "An About dialog titled '{}' with application information.",
    "file_properties": "A Properties dialog titled '{}' with file metadata and attributes.",
    "default": "A desktop application window titled '{}'.",
}


def parse_yolo_label(label_path: str, img_width: int = 1280, img_height: int = 720):
    """Parse YOLO format .txt label file.

    Returns:
        List of (class_id, x1, y1, x2, y2, class_name) in pixel coords.
    """
    elements = []
    if not os.path.exists(label_path):
        return elements

    with open(label_path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            cls_id = int(parts[0])
            x_center = float(parts[1]) * img_width
            y_center = float(parts[2]) * img_height
            width = float(parts[3]) * img_width
            height = float(parts[4]) * img_height

            x1 = int(x_center - width / 2)
            y1 = int(y_center - height / 2)
            x2 = int(x_center + width / 2)
            y2 = int(y_center + height / 2)

            elements.append({
                "class_id": cls_id,
                "class_name": CLASS_NAMES.get(cls_id, f"unknown_{cls_id}"),
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            })

    return elements


def detect_scene_type(elements) -> str:
    """Heuristic scene type detection from element composition."""
    class_counts = {}
    for e in elements:
        cn = e["class_name"]
        class_counts[cn] = class_counts.get(cn, 0) + 1

    has_dialog = class_counts.get("dialog", 0) > 0
    has_menu_bar = class_counts.get("menu_bar", 0) > 0
    has_text_area = class_counts.get("text_area", 0) > 0
    has_close = class_counts.get("close_button", 0) > 0
    has_progress = class_counts.get("progress_bar", 0) > 0
    has_tabs = class_counts.get("tab", 0) > 0
    has_radio = class_counts.get("radio", 0) > 0
    has_checkbox = class_counts.get("checkbox", 0) > 0
    has_text_field = class_counts.get("text_field", 0) > 0
    has_dropdown = class_counts.get("dropdown", 0) > 0
    has_taskbar = class_counts.get("taskbar", 0) > 0

    if has_progress:
        return "wizard" if has_dialog else "control_panel"
    if has_tabs and has_checkbox:
        return "settings"
    if has_dialog and has_text_field and has_dropdown:
        return "save_dialog"
    if has_dialog and has_text_area and not has_menu_bar:
        return "error_dialog"
    if has_dialog and has_radio:
        return "wizard"
    if has_menu_bar and has_text_area and not has_dialog:
        return "notepad"
    if has_menu_bar and has_checkbox:
        return "settings"
    if has_dialog and has_progress:
        return "wizard"
    if has_text_area and has_text_field:
        return "control_panel"
    if has_taskbar and has_close and len(elements) > 15:
        return "multi_window"
    if has_menu_bar and (has_list := class_counts.get("list_item", 0)) > 0:
        return "file_manager"
    if has_dialog and has_text_field:
        return "save_dialog"

    return "default"


def generate_caption(elements, scene_type: str) -> str:
    """Generate a natural language caption from detected elements."""
    if not elements:
        return "A blank or empty desktop screen."

    class_counts = {}
    for e in elements:
        cn = e["class_name"]
        class_counts[cn] = class_counts.get(cn, 0) + 1

    # Get title if available
    title_el = [e for e in elements if e["class_name"] == "title_text"]
    title_text = ""
    for e in title_el:
        if e["x2"] - e["x1"] > 20:
            title_text = "a window"  # Would need OCR for actual text
            break

    # Build caption from scene pattern + element enumeration
    if scene_type in SCENE_PATTERNS:
        caption = SCENE_PATTERNS[scene_type].format("application window" if not title_text else title_text)
    else:
        caption = SCENE_PATTERNS["default"].format("application window" if not title_text else title_text)

    # Add element details for key interactive elements
    details = []
    for cn in ["close_button", "button", "text_field", "dropdown", "checkbox",
               "radio", "menu_item", "tab", "progress_bar", "spinner_button",
               "link", "textarea", "scrollbar", "list_item"]:
        count = class_counts.get(cn, 0)
        if count > 0:
            plural = "s" if count > 1 else ""
            details.append(f"{count} {CLASS_DESCRIPTORS.get([k for k,v in CLASS_NAMES.items() if v==cn][0], cn)}{plural}" if False else f"{count} {cn.replace('_', ' ')}{plural}")

    # Use lookup correctly
    detail_parts = []
    for cn_singular, count in sorted(class_counts.items()):
        if cn_singular in ("title_bar", "title_text", "taskbar", "dialog",
                            "toolbar", "status_bar", "menu_bar", "icon"):
            continue
        plural = "s" if count > 1 else ""
        desc = cn_singular.replace("_", " ")
        detail_parts.append(f"{count} {desc}{plural}")

    if detail_parts:
        caption += " Contains " + ", ".join(detail_parts[:-1])
        if len(detail_parts) > 1:
            caption += ", and " + detail_parts[-1]
        else:
            caption += detail_parts[0]

    # Add spatial organization hints
    if class_counts.get("tab", 0) > 0:
        caption += " organized in tabs."
    elif class_counts.get("menu_bar", 0) > 0:
        caption += " with a menu bar at the top."
    else:
        caption += "."

    return caption


def generate_short_caption(elements) -> str:
    """Generate a brief one-line caption."""
    class_counts = {}
    for e in elements:
        cn = e["class_name"]
        class_counts[cn] = class_counts.get(cn, 0) + 1

    scene_type = detect_scene_type(elements)

    # Scene labels
    scene_labels = {
        "save_dialog": "Save dialog",
        "settings": "Settings window",
        "error_dialog": "Error dialog",
        "notepad": "Notepad editor",
        "control_panel": "Control panel",
        "file_manager": "File manager",
        "browser": "Browser window",
        "terminal": "Terminal window",
        "context_menu": "Context menu",
        "wizard": "Wizard dialog",
        "multi_window": "Multi-window desktop",
        "about_dialog": "About dialog",
        "file_properties": "Properties dialog",
    }
    label = scene_labels.get(scene_type, "Desktop window")

    # Count key elements
    interactive = sum(class_counts.get(cn, 0) for cn in
                      ["button", "close_button", "text_field", "dropdown",
                       "checkbox", "radio", "tab"])
    return f"{label} with {interactive} interactive elements."


def generate_detailed_caption(elements, scene_type: str) -> str:
    """Generate a detailed structured caption suitable for training."""
    caption = generate_caption(elements, scene_type)
    short = generate_short_caption(elements)
    return f"{short}\nDescription: {caption}"


def main():
    parser = argparse.ArgumentParser(description="Generate Florence-2 caption training data")
    parser.add_argument("--dataset", default="/models/wine-dataset-10k",
                        help="Dataset root directory")
    parser.add_argument("--output", default="/models/florence2-training/captions.jsonl",
                        help="Output JSONL path")
    parser.add_argument("--split", default="train",
                        choices=["train", "val", "test", "all"],
                        help="Which split to process")
    parser.add_argument("--max-samples", type=int, default=5000,
                        help="Max training pairs to generate")
    parser.add_argument("--style", default="detailed",
                        choices=["brief", "detailed", "functional", "all"],
                        help="Caption style")
    args = parser.parse_args()

    dataset_dir = args.dataset
    output_path = args.output

    splits = ["train", "val", "test"] if args.split == "all" else [args.split]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    total = 0
    with open(output_path, "w") as out_f:
        for split in splits:
            images_dir = os.path.join(dataset_dir, split, "images")
            labels_dir = os.path.join(dataset_dir, split, "labels")

            if not os.path.isdir(images_dir):
                print(f"  SKIP: {images_dir} not found", file=sys.stderr)
                continue

            image_files = sorted([
                f for f in os.listdir(images_dir)
                if f.endswith((".png", ".jpg"))
            ])

            print(f"Processing {split}: {len(image_files)} images", file=sys.stderr)

            for img_file in image_files:
                if total >= args.max_samples:
                    break

                img_path = os.path.join(images_dir, img_file)
                label_file = os.path.splitext(img_file)[0] + ".txt"
                label_path = os.path.join(labels_dir, label_file)

                elements = parse_yolo_label(label_path)
                scene_type = detect_scene_type(elements)

                if args.style == "brief":
                    caption = generate_short_caption(elements)
                elif args.style == "functional":
                    caption = generate_caption(elements, scene_type)
                else:  # detailed or all
                    caption = generate_detailed_caption(elements, scene_type)

                record = {
                    "image_path": img_path,
                    "caption": caption,
                    "style": args.style if args.style != "all" else "detailed",
                    "scene_type": scene_type,
                    "split": split,
                    "num_elements": len(elements),
                }
                out_f.write(json.dumps(record) + "\n")
                total += 1

                if total % 500 == 0:
                    print(f"  Generated {total} pairs...", file=sys.stderr)

                if total >= args.max_samples:
                    break

            if total >= args.max_samples:
                break

    print(f"\nDone! Generated {total} caption pairs to {output_path}", file=sys.stderr)
    print(f"Estimated LoRA training time: ~{total // 1000 + 1} hours on RTX 3090", file=sys.stderr)


if __name__ == "__main__":
    main()
