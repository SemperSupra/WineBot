#!/usr/bin/env python3
# EXECUTION: IN_CONTAINER — reads CV watcher output from container filesystem
# STATUS: ACTIVE — warning detection for CV watcher data; run by stop_recording() auto-analysis
"""Analyze CV watcher JSONL output. Reports warnings, failures, errors."""

import json
import sys


def analyze(log_path: str, start_frame: int = 0) -> dict:
    """Parse watcher.jsonl and return issues found.

    Args:
        log_path: Path to watcher.jsonl
        start_frame: 0 = auto-detect content start (first frame with >10Kpx change).
                     N > 0 = skip first N frames.
    """
    snapshots: list[dict] = []
    with open(log_path) as f:
        for line in f:
            try:
                snapshots.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    # Auto-detect content start if start_frame == 0
    content_start = start_frame
    if start_frame == 0:
        for snap in snapshots:
            if snap.get("event") != "snapshot":
                continue
            if snap.get("pixels_changed", 0) > 10000:
                content_start = max(0, snap["index"] - 2)  # 2 frames before big change
                break

    issues = []
    warning_windows = {"Save As", "Open", "Error", "Warning", "Critical",
                       "Assertion Failed", "Wine C++ Runtime", "wine",
                       "X Error", "BadWindow", "abort", "Segmentation fault"}
    persistent_unknown = {}

    for i, snap in enumerate(snapshots):
        if snap.get("event") != "snapshot":
            continue

        idx = snap["index"]
        # Skip frames before content starts (stale windows from prior sessions)
        if idx < content_start:
            continue

        interesting = set(snap.get("interesting_windows", []))
        all_titles = {w["title"] for w in snap.get("windows", [])}
        pixels = snap.get("pixels_changed", 0)

        # Check for warning windows
        warnings_found = interesting & warning_windows
        # Also scan all titles for embedded warnings
        for title in all_titles:
            if any(w.lower() in title.lower() for w in ("error", "fail", "abort",
                   "denied", "not found", "cannot", "unable")):
                warnings_found.add(title)

        if warnings_found:
            issues.append({
                "type": "WARNING_WINDOW",
                "severity": "HIGH",
                "frame": idx,
                "windows": sorted(warnings_found),
                "message": f"Frame {idx}: warning/error windows visible: {sorted(warnings_found)}"
            })

        # Check for unexpected pixel changes
        if pixels > 50000 and idx > 0:
            prev = snapshots[i - 1] if i > 0 else {}
            prev_windows = set(w["title"] for w in prev.get("windows", []))
            new_windows = all_titles - prev_windows
            closed_windows = prev_windows - all_titles
            if new_windows:
                issues.append({
                    "type": "LARGE_CHANGE",
                    "severity": "INFO",
                    "frame": idx,
                    "pixels": pixels,
                    "new_windows": sorted(new_windows - {"N/A", ""}),
                    "closed_windows": sorted(closed_windows - {"N/A", ""}),
                    "message": f"Frame {idx}: {pixels}px change. New: {sorted(new_windows - {'N/A',''})}"
                })

        # Track persistent windows (same window visible across many frames)
        for title in all_titles:
            if title in ("N/A", "", "Openbox", "tint2"):
                continue
            persistent_unknown[title] = persistent_unknown.get(title, 0) + 1

    # Flag windows that persist too long (possible leaks)
    total_frames = len(snapshots)
    for title, count in persistent_unknown.items():
        ratio = count / max(total_frames, 1)
        if ratio > 0.9 and title not in ("Openbox", "tint2"):
            # Window visible in >90% of frames — check if it should close
            if any(close_word in title for close_word in
                   ("Save", "Error", "Warning", "Notepad", "cmd", "Registry")):
                # These should close at some point
                pass  # Tracked separately if they appear in warning_windows
            else:
                issues.append({
                    "type": "PERSISTENT_WINDOW",
                    "severity": "LOW",
                    "window": title,
                    "frames": count,
                    "ratio": f"{ratio:.1%}",
                    "message": f"Window '{title}' visible in {count}/{total_frames} frames ({ratio:.1%})"
                })

    # Key events timeline
    events = []
    last_windows: set[str] = set()
    for snap in snapshots:
        if snap.get("event") != "snapshot":
            continue
        current = set(snap.get("interesting_windows", []))
        appeared = current - last_windows
        disappeared = last_windows - current
        if appeared or disappeared:
            events.append({
                "frame": snap["index"],
                "appeared": sorted(appeared),
                "disappeared": sorted(disappeared),
                "pixels": snap.get("pixels_changed", 0),
            })
        last_windows = current

    content_frames = len([s for s in snapshots if s.get("event") == "snapshot" and s.get("index", 0) >= content_start])
    return {
        "summary": {
            "total_frames": len(snapshots),
            "content_frames": content_frames,
            "content_start": content_start,
            "total_issues": len(issues),
            "high_severity": len([i for i in issues if i["severity"] == "HIGH"]),
            "medium_severity": len([i for i in issues if i["severity"] == "MEDIUM"]),
            "low_severity": len([i for i in issues if i["severity"] == "LOW"]),
        },
        "issues": issues,
        "timeline": events,
    }


def main():
    log_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/winebot_watcher/watcher.jsonl"

    try:
        report = analyze(log_path)
    except FileNotFoundError:
        print(f"ERROR: Log file not found: {log_path}")
        sys.exit(1)

    s = report["summary"]
    print("=" * 70)
    print("CV ANALYSIS REPORT")
    print(f"  Frames: {s['total_frames']}")
    print(f"  Issues: {s['total_issues']} ({s['high_severity']} high, "
          f"{s['medium_severity']} medium, {s['low_severity']} low)")
    print()

    if report["issues"]:
        print("--- ISSUES ---")
        for issue in report["issues"]:
            tag = {"HIGH": "!! HIGH !!", "MEDIUM": "! MEDIUM",
                   "LOW": "low", "INFO": "info"}[issue["severity"]]
            print(f"  [{issue['frame']:03d}] {tag:12s} {issue['message']}")
        print()

    print("--- WINDOW APPEARANCE TIMELINE ---")
    for evt in report["timeline"]:
        ap = ", ".join(evt["appeared"]) if evt["appeared"] else "—"
        dp = ", ".join(evt["disappeared"]) if evt["disappeared"] else "—"
        print(f"  [{evt['frame']:03d}] +{ap:<35s}  -{dp}")

    print()
    if s["high_severity"] > 0:
        print("RESULT: ISSUES FOUND — review warnings above")
        sys.exit(1)
    else:
        print("RESULT: CLEAN — no high-severity issues detected")
        sys.exit(0)


if __name__ == "__main__":
    main()
