#!/usr/bin/env python3
"""Capture real desktop screenshots from Windows for pipeline validation.

Captures screenshots of the actual Windows desktop with any visible
applications, then copies them into the CV sidecar container for
pipeline analysis.

Usage:
  python3 capture_real_desktop.py
"""
import os, time, subprocess, sys
from pathlib import Path

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "demo", "output", "real-desktop-frames")
CONTAINER = "winebot-cv"
CONTAINER_PATH = "/tmp/real-desktop-frames"


def capture_screenshot(filename: str):
    """Capture a screenshot using PowerShell."""
    path = os.path.join(OUTPUT_DIR, filename)
    ps_cmd = f"""
    Add-Type -AssemblyName System.Windows.Forms
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bitmap = New-Object System.Drawing.Bitmap $screen.Width, $screen.Height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen($screen.X, $screen.Y, 0, 0, $bitmap.Size)
    $bitmap.Save('{path}', [System.Drawing.Imaging.ImageFormat]::Png)
    $graphics.Dispose()
    $bitmap.Dispose()
    """
    result = subprocess.run(
        ["powershell", "-Command", ps_cmd],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr.strip()}")
        return False
    return True


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 60)
    print("  Real Desktop Screenshot Capture")
    print("=" * 60)
    print()
    print("  This will capture your actual Windows desktop.")
    print("  Please prepare the following scenes:")
    print()

    scenes = [
        ("empty_desktop", "Minimize all windows, show clean desktop"),
        ("notepad", "Open Notepad with some text"),
        ("file_explorer", "Open File Explorer to a folder"),
        ("browser", "Open a web browser"),
        ("settings", "Open Windows Settings"),
        ("run_dialog", "Press Win+R to open Run dialog"),
        ("task_manager", "Open Task Manager"),
        ("save_dialog", "Open any app and trigger File > Save As"),
        ("multiple_windows", "Open 2-3 windows overlapping"),
        ("context_menu", "Right-click on desktop for context menu"),
    ]

    for i, (name, instruction) in enumerate(scenes):
        input(f"  Step {i+1}: {instruction}")
        print(f"  Capturing {name}...")
        capture_screenshot(f"{name}.png")
        print(f"  Saved {name}.png\n")

    # Copy to container
    print("Copying to container...")
    os.makedirs(CONTAINER_PATH, exist_ok=True)
    for f in os.listdir(OUTPUT_DIR):
        if f.endswith(".png"):
            result = subprocess.run(
                ["docker", "cp", os.path.join(OUTPUT_DIR, f),
                 f"{CONTAINER}:{CONTAINER_PATH}/{f}"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                print(f"  ERROR copying {f}: {result.stderr.strip()}")

    print(f"\nDone! {len(os.listdir(OUTPUT_DIR))} screenshots captured.")
    print(f"Local: {OUTPUT_DIR}")
    print(f"Container: {CONTAINER}:{CONTAINER_PATH}/")


if __name__ == "__main__":
    main()
