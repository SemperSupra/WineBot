#!/usr/bin/env python3
# EXECUTION: IN_CONTAINER — requires Wine desktop screenshot (ImageMagick/xwd), API access
# STATUS: ACTIVE — pixel-diff desktop monitor; auto-started by _demo_common.sh init_session()
"""CV Watcher: monitors the WineBot desktop during automation.

Takes periodic screenshots, diffs consecutive frames to detect visual
changes, and logs window inventories.  Used to diagnose why interactions
fail — shows exactly what appeared on screen at each step.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple


class CVWatcher:
    def __init__(self, output_dir: str, api_url: str = "http://localhost:8000"):
        self.output_dir = output_dir
        self.api_url = api_url
        self.frame_index = 0
        self.last_frame: Optional[str] = None
        self.history: List[Dict] = []
        self._token: Optional[str] = None

        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(os.path.join(output_dir, "frames"), exist_ok=True)

        # Check screenshot capability at startup
        self._has_import = self._check_cmd(["import", "-version"])
        self._has_xwd = self._check_cmd(["xwd", "-version"])
        if not self._has_import and not self._has_xwd:
            print("WARNING: Neither 'import' (ImageMagick) nor 'xwd' found — screenshots may fail",
                  file=sys.stderr)

        # Write header
        self._log_path = os.path.join(output_dir, "watcher.jsonl")
        with open(self._log_path, "w") as f:
            f.write(
                json.dumps(
                    {
                        "event": "watcher_start",
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "api_url": api_url,
                    }
                )
                + "\n"
            )

    @staticmethod
    def _check_cmd(cmd: list) -> bool:
        """Check if a command is available."""
        try:
            subprocess.run(cmd, capture_output=True, timeout=3)
            return True
        except Exception:
            return False

    def _token_from_container(self) -> Optional[str]:
        """Read API token from container filesystem."""
        for path in ("/tmp/winebot_api_token", "/winebot-shared/winebot_api_token"):
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        return f.read().strip()
                except Exception:
                    pass
        return None

    @property
    def token(self) -> str:
        if self._token is None:
            self._token = self._token_from_container() or ""
        return self._token

    def _curl(self, method: str, path: str, data: Optional[str] = None) -> dict:
        """Minimal API call via subprocess curl."""
        cmd = ["curl", "-s"]
        if self.token:
            cmd.extend(["-H", f"X-API-Key: {self.token}"])
        if method == "POST":
            cmd.append("-X")
            cmd.append("POST")
        if data:
            cmd.extend(["-H", "Content-Type: application/json", "-d", data])
        cmd.append(f"{self.api_url}{path}")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return json.loads(result.stdout) if result.stdout else {}
        except Exception:
            return {}

    def _capture_frame(self) -> str:
        """Capture a screenshot and return the file path."""
        import_path = os.path.join(self.output_dir, "frames", f"frame_{self.frame_index:04d}.png")
        try:
            subprocess.run(
                ["import", "-window", "root", import_path],
                capture_output=True,
                timeout=5,
            )
            if os.path.exists(import_path):
                return import_path
        except Exception:
            pass

        # Fallback: xdotool-based capture via xwd
        try:
            xwd_path = os.path.join(self.output_dir, f"tmp_{self.frame_index}.xwd")
            subprocess.run(
                ["xdotool", "getactivewindow"],
                capture_output=True,
                timeout=3,
            )
            subprocess.run(
                ["xwd", "-root", "-out", xwd_path],
                capture_output=True,
                timeout=5,
            )
            subprocess.run(
                ["convert", f"xwd:{xwd_path}", import_path],
                capture_output=True,
                timeout=5,
            )
            os.remove(xwd_path)
            if os.path.exists(import_path):
                return import_path
        except Exception:
            pass

        return ""

    def _window_inventory(self) -> List[Dict]:
        """List all visible windows with their titles and classes."""
        try:
            result = subprocess.run(
                ["xdotool", "search", "--onlyvisible", ""],
                capture_output=True,
                text=True,
                timeout=5,
            )
            ids = result.stdout.strip().split("\n") if result.stdout.strip() else []
        except Exception:
            ids = []

        windows = []
        for wid_str in ids:
            wid = wid_str.strip()
            if not wid:
                continue
            try:
                name = subprocess.run(
                    ["xdotool", "getwindowname", wid],
                    capture_output=True,
                    text=True,
                    timeout=3,
                ).stdout.strip()
            except Exception:
                name = ""

            try:
                cls = subprocess.run(
                    ["xprop", "-id", wid, "WM_CLASS"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                ).stdout.strip()
            except Exception:
                cls = ""

            try:
                geo = subprocess.run(
                    ["xdotool", "getwindowgeometry", "--shell", wid],
                    capture_output=True,
                    text=True,
                    timeout=3,
                ).stdout.strip()
            except Exception:
                geo = ""

            if name and name != "N/A":
                windows.append(
                    {"id": wid, "title": name, "class": cls, "geometry": geo}
                )

        return windows

    def _compute_diff(self, a: str, b: str) -> Dict:
        """Compare two frames using ImageMagick compare."""
        diff_pixels = 0
        try:
            result = subprocess.run(
                ["compare", "-metric", "AE", a, b, "null:"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            # compare outputs metric to stderr
            raw = result.stderr.strip()
            try:
                diff_pixels = int(raw)
            except ValueError:
                pass
        except Exception:
            pass

        # Also create a diff image if > 0 pixels changed
        diff_path = ""
        if diff_pixels > 0:
            diff_path = os.path.join(
                self.output_dir, "frames", f"diff_{self.frame_index:04d}.png"
            )
            try:
                subprocess.run(
                    ["compare", a, b, diff_path],
                    capture_output=True,
                    timeout=10,
                )
            except Exception:
                diff_path = ""

        return {"pixels_changed": diff_pixels, "diff_image": diff_path}

    def snapshot(self, label: str = "", step: str = "") -> Dict:
        """Take a snapshot: capture frame, inventory windows, diff vs last.

        Returns a summary dict suitable for logging.
        """
        ts = datetime.now(timezone.utc).isoformat()
        timestamp_ms = int(time.time() * 1000)

        # Capture
        frame_path = self._capture_frame()
        windows = self._window_inventory()
        frame_size = os.path.getsize(frame_path) if frame_path else 0

        # Diff vs previous frame
        diff = {}
        if self.last_frame and frame_path and os.path.exists(self.last_frame):
            diff = self._compute_diff(self.last_frame, frame_path)

        # Build report
        report = {
            "event": "snapshot",
            "index": self.frame_index,
            "label": label,
            "step": step,
            "timestamp_utc": ts,
            "timestamp_epoch_ms": timestamp_ms,
            "frame_path": frame_path,
            "frame_size_bytes": frame_size,
            "windows_count": len(windows),
            "windows": windows,
            "pixels_changed": diff.get("pixels_changed", 0),
            "diff_image": diff.get("diff_image", ""),
        }

        # Check for specific windows of interest
        interest = ["Save As", "Open", "WineBot", "Notepad", "Registry", "cmd",
                     "tint2", "Openbox", "Error", "Warning", "Confirm", "WineBot Save Dialog"]
        found_interesting = [w["title"] for w in windows
                            if any(k in w["title"] for k in interest)]
        report["interesting_windows"] = found_interesting

        # Log to JSONL
        with open(self._log_path, "a") as f:
            f.write(json.dumps(report) + "\n")

        # Print summary to stdout
        print(
            f"  [CV:{self.frame_index:03d}] "
            f"Δ={report['pixels_changed']:>6}px  "
            f"windows={len(windows):>3}  "
            f"interesting={found_interesting}"
        )

        self.frame_index += 1
        self.last_frame = frame_path
        self.history.append(report)
        return report

    def generate_report(self) -> str:
        """Generate a human-readable HTML report."""
        html_path = os.path.join(self.output_dir, "report.html")

        rows = []
        for snap in self.history:
            windows_str = ", ".join(
                f"{w['title']}" for w in snap.get("windows", [])[:10]
            )
            rows.append(
                f"<tr>"
                f"<td>{snap['index']}</td>"
                f"<td>{snap['label']}</td>"
                f"<td>{snap['pixels_changed']}</td>"
                f"<td>{snap['windows_count']}</td>"
                f"<td>{snap.get('interesting_windows', [])}</td>"
                f"<td>{snap['frame_size_bytes']}</td>"
                f"</tr>"
            )

        html = f"""<!DOCTYPE html>
<html><head><title>WineBot CV Watcher Report</title>
<style>
  body {{ font-family: sans-serif; margin: 20px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 6px 10px; text-align: left; }}
  th {{ background: #1A2340; color: white; }}
  tr:nth-child(even) {{ background: #f5f5f5; }}
  .change {{ background: #fff3cd; }}
  .big-change {{ background: #ffc107; font-weight: bold; }}
</style></head><body>
<h1>WineBot CV Watcher Report</h1>
<p>Session: {self.output_dir}</p>
<h2>Snapshots</h2>
<table>
<tr><th>#</th><th>Label</th><th>Pixel Δ</th><th>Windows</th><th>Interesting</th><th>Frame KB</th></tr>
{"".join(rows)}
</table>
<h2>Frame Sequence</h2>
<p>Frames are in {self.output_dir}/frames/</p>
<ul>
"""
        for snap in self.history:
            html += f'<li><strong>#{snap["index"]}</strong>: {snap["label"]} '
            html += f'(Δ={snap["pixels_changed"]}px) '
            if snap.get("frame_path"):
                html += f'<br><img src="frames/{os.path.basename(snap["frame_path"])}" style="max-width:640px">'
            html += "</li>\n"

        html += "</ul></body></html>"

        with open(html_path, "w") as f:
            f.write(html)

        return html_path


def main():
    parser = argparse.ArgumentParser(description="CV Watcher for WineBot diagnostics")
    parser.add_argument("--output-dir", default="/tmp/winebot_watcher")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--interval", type=float, default=0.5,
                        help="Seconds between snapshots in watch mode")
    parser.add_argument("--watch", action="store_true",
                        help="Continuous monitoring mode")
    parser.add_argument("--duration", type=int, default=300,
                        help="Max watch duration in seconds")
    parser.add_argument("--label", default="manual",
                        help="Label for this session")
    args = parser.parse_args()

    watcher = CVWatcher(output_dir=args.output_dir, api_url=args.api_url)

    print(f"CV Watcher started — output: {args.output_dir}")
    print(f"  API: {args.api_url}  Token: {'found' if watcher.token else 'none'}")
    print(f"  Mode: {'continuous watch' if args.watch else 'one-shot'}")
    print()

    if args.watch:
        start = time.time()
        while time.time() - start < args.duration:
            watcher.snapshot(label=args.label, step=f"auto_{int(time.time() - start)}s")
            time.sleep(args.interval)
    else:
        watcher.snapshot(label=args.label, step="single")

    report_path = watcher.generate_report()
    print(f"\nReport: {report_path}")
    print(f"Frames: {args.output_dir}/frames/")
    print(f"Log:    {args.output_dir}/watcher.jsonl")


if __name__ == "__main__":
    main()
