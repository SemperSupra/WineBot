#!/usr/bin/env python3
# EXECUTION: HOST — batch processes MKV files; CI gate; needs ffmpeg+OpenCV
# STATUS: ACTIVE — CI gate (--exit-on-warnings); batch runner for all demo videos
"""CV Batch Analyzer — runs CV/OCR pipeline over all MKV files in a directory.

Generates a unified report showing which videos pass visual checks and which
have warnings. Designed as a CI/CD gate — returns exit code 1 if any
HIGH-severity warnings are found.

Calls cv-test-runner.py as a subprocess for each video.

Usage:
  python3 scripts/diagnostics/cv-batch-analyze.py --input demo/output/
  python3 scripts/diagnostics/cv-batch-analyze.py --input demo/output/ --exit-on-warnings

Exit codes:
  0 — all clean, no warnings
  1 — HIGH-severity warnings found
  2 — processing error (missing files, dependencies)
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

# Check if Tesseract is available
try:
    import pytesseract  # noqa: F401
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False


class BatchAnalyzer:
    """Runs CV analysis over all MKV files in a directory."""

    def __init__(self, input_dir: str, output_dir: str = "",
                 frame_interval: float = 1.0, mode: str = "built-in"):
        self.input_dir = Path(input_dir)
        if not self.input_dir.is_dir():
            raise NotADirectoryError(f"Not a directory: {input_dir}")

        if output_dir:
            self.out_dir = Path(output_dir)
        else:
            self.out_dir = self.input_dir / "analysis"
        self.out_dir.mkdir(parents=True, exist_ok=True)

        self.frame_interval = frame_interval
        self.mode = mode
        self.results: dict[str, dict] = {}

        # Locate cv-test-runner.py
        script_dir = Path(__file__).resolve().parent
        self.runner_script = script_dir / "cv-test-runner.py"

    def find_videos(self) -> list[Path]:
        """Find all .mkv files in input directory."""
        videos = sorted(self.input_dir.glob("*.mkv"))
        # Filter out _part files
        videos = [v for v in videos if "_part" not in v.stem]
        return videos

    def _run_one(self, video: Path, out_dir: Path) -> dict:
        """Run cv-test-runner.py on a single video, return parsed summary."""
        cmd = [
            sys.executable, str(self.runner_script),
            "--video", str(video),
            "--output", str(out_dir),
            "--frame-interval", str(self.frame_interval),
            "--mode", self.mode,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                stderr = result.stderr[-500:] if len(result.stderr) > 500 else result.stderr
                return {"error": f"exit_code={result.returncode}", "stderr": stderr}
        except subprocess.TimeoutExpired:
            return {"error": "timeout after 300s"}

        # Read the summary.json produced by cv-test-runner.py
        summary_path = out_dir / "summary.json"
        if summary_path.exists():
            with open(summary_path) as f:
                return json.load(f)
        return {"error": "no summary generated", "video": str(video)}

    def run(self) -> dict:
        """Run CV analysis on all videos, return unified report."""
        videos = self.find_videos()
        if not videos:
            print("ERROR: No MKV files found in input directory")
            return {"error": "no_videos", "input_dir": str(self.input_dir)}

        if not self.runner_script.exists():
            print(f"ERROR: Runner script not found: {self.runner_script}")
            return {"error": "runner_missing"}

        print("CV Batch Analyzer")
        print(f"  Input:  {self.input_dir}")
        print(f"  Videos: {len(videos)}")
        print(f"  Mode:   {self.mode}")
        print(f"  Runner: {self.runner_script}")
        print(f"  Tesseract: {'available' if HAS_TESSERACT else 'NOT AVAILABLE'}")
        print()

        start_time = time.time()

        for i, video in enumerate(videos):
            vid_name = video.stem
            vid_out = self.out_dir / vid_name
            vid_out.mkdir(parents=True, exist_ok=True)

            print(f"[{i+1}/{len(videos)}] {vid_name}", end="", flush=True)

            summary = self._run_one(video, vid_out)
            self.results[vid_name] = summary

            if "error" in summary:
                print(f"  FAIL {summary['error']}")
            else:
                frames = summary.get("frames_analyzed", 0)
                warnings = summary.get("total_warnings", 0)
                targets = summary.get("frames_with_click_targets", 0)
                print(f"  OK {frames} frames, {targets} targets, {warnings} warnings")

        elapsed = time.time() - start_time

        # Build unified report
        report = self._build_report(elapsed)

        # Write report
        report_path = self.out_dir / "batch_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        # Print summary
        self._print_summary(report)

        return report

    def _build_report(self, elapsed_s: float) -> dict:
        total_frames = 0
        total_warnings = 0
        total_targets = 0
        per_video = {}
        passed = []
        warnings_list = []
        failed = []

        for name, r in self.results.items():
            if "error" in r:
                failed.append({"name": name, "error": r["error"]})
                continue

            frames = r.get("frames_analyzed", 0)
            warns = r.get("total_warnings", 0)
            targets = r.get("frames_with_click_targets", 0)

            total_frames += frames
            total_warnings += warns
            total_targets += targets

            info = {
                "name": name,
                "frames_analyzed": frames,
                "frames_with_click_targets": targets,
                "warnings": warns,
                "ui_states": r.get("ui_states", {}),
                "click_targets_timeline": r.get("click_targets_timeline", []),
                "output_dir": r.get("output_dir", ""),
            }
            per_video[name] = info

            if warns > 0:
                warnings_list.append(info)
            else:
                passed.append(info)

        return {
            "batch_summary": {
                "input_dir": str(self.input_dir),
                "videos_total": len(self.results),
                "videos_passed": len(passed),
                "videos_with_warnings": len(warnings_list),
                "videos_failed": len(failed),
                "total_frames_analyzed": total_frames,
                "total_click_targets": total_targets,
                "total_warnings": total_warnings,
                "elapsed_seconds": round(elapsed_s, 1),
                "mode": self.mode,
                "tesseract_available": HAS_TESSERACT,
            },
            "passed": passed,
            "warnings": warnings_list,
            "failed": failed,
            "per_video": per_video,
        }

    def _print_summary(self, report: dict):
        s = report["batch_summary"]
        print()
        print("=" * 70)
        print("  BATCH CV ANALYSIS COMPLETE")
        print(f"  Videos: {s['videos_total']} total | "
              f"{s['videos_passed']} clean | "
              f"{s['videos_with_warnings']} warnings | "
              f"{s['videos_failed']} failed")
        print(f"  Frames: {s['total_frames_analyzed']} analyzed")
        print(f"  Click targets: {s['total_click_targets']}")
        print(f"  Warnings: {s['total_warnings']}")
        print(f"  Time: {s['elapsed_seconds']}s")
        print()

        if report["passed"]:
            print("  [PASS] PASSED (no warnings):")
            for v in report["passed"]:
                print(f"     {v['name']}: {v['frames_analyzed']} frames")
            print()

        if report["warnings"]:
            print("  [WARN] WARNINGS:")
            for v in report["warnings"]:
                targets_str = f", targets in {v['frames_with_click_targets']} frames" if v['frames_with_click_targets'] else ""
                print(f"     {v['name']}: {v['warnings']} warnings{targets_str}")
            print()

        if report["failed"]:
            print("  [FAIL] FAILED:")
            for v in report["failed"]:
                print(f"     {v['name']}: {v['error']}")
            print()

        print(f"  Report: {self.out_dir / 'batch_report.json'}")
        print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Batch CV analyzer for WineBot demo videos")
    parser.add_argument("--input", required=True,
                        help="Directory containing MKV files to analyze")
    parser.add_argument("--output", default="",
                        help="Output directory for analysis results")
    parser.add_argument("--frame-interval", type=float, default=1.0,
                        help="Seconds between extracted frames")
    parser.add_argument("--mode", choices=["built-in", "full"], default="built-in")
    parser.add_argument("--exit-on-warnings", action="store_true",
                        help="Exit with code 1 if warnings found (CI gate)")
    args = parser.parse_args()

    try:
        analyzer = BatchAnalyzer(
            input_dir=args.input,
            output_dir=args.output,
            frame_interval=args.frame_interval,
            mode=args.mode,
        )
    except NotADirectoryError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    try:
        report = analyzer.run()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(2)

    # CI gate: exit 1 if warnings found
    if args.exit_on_warnings:
        total_warnings = report.get("batch_summary", {}).get("total_warnings", 0)
        failed_count = report.get("batch_summary", {}).get("videos_failed", 0)
        if total_warnings > 0 or failed_count > 0:
            print(f"\n[CI GATE] {total_warnings} warnings, {failed_count} failures — exiting with code 1")
            sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
