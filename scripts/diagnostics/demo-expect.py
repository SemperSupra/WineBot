#!/usr/bin/env python3
# EXECUTION: HOST — reads expected_states.jsonl + watcher.jsonl from artifacts/; CI gate
# STATUS: ACTIVE — post-run assertion checker; validates demo windows appeared on schedule
"""Demo expectation checker — post-run assertion engine.

Reads expected_states.jsonl (written by `ann_expect()` during a demo) and
validates that expected windows appeared within a time tolerance using
CV watcher data or window snapshot data.

Usage:
  python3 scripts/diagnostics/demo-expect.py --session-dir /sessions/session-abc123

Exit codes:
  0 — all assertions pass
  1 — one or more assertions fail
  2 — no data found
"""

import argparse
import json
import sys
from pathlib import Path


class DemoExpectChecker:
    """Checks expected-state assertions against CV watcher data."""

    def __init__(self, session_dir: str, tolerance_s: float = 5.0):
        self.session_dir = Path(session_dir)
        self.analysis_dir = self.session_dir / "analysis"
        self.tolerance_s = tolerance_s

    def load_expected_states(self) -> list[dict]:
        """Load expected state assertions from expected_states.jsonl."""
        path = self.analysis_dir / "expected_states.jsonl"
        if not path.exists():
            return []
        states = []
        with open(path) as f:
            for line in f:
                try:
                    e = json.loads(line)
                    if e.get("kind") == "expected_state":
                        states.append(e)
                except json.JSONDecodeError:
                    continue
        return states

    def load_cv_data(self) -> list[dict]:
        """Load CV watcher snapshots or window snapshots."""
        # Prefer watcher data
        watcher_path = self.analysis_dir / "cv" / "watcher.jsonl"
        if watcher_path.exists():
            snapshots = []
            with open(watcher_path) as f:
                for line in f:
                    try:
                        snap = json.loads(line)
                        if snap.get("event") == "snapshot":
                            snapshots.append(snap)
                    except json.JSONDecodeError:
                        continue
            return snapshots

        # Fall back to demo snapshots
        snap_path = self.analysis_dir / "snapshots.jsonl"
        if snap_path.exists():
            snapshots = []
            with open(snap_path) as f:
                for line in f:
                    try:
                        snap = json.loads(line)
                        if snap.get("kind") == "snapshot":
                            snapshots.append(snap)
                    except json.JSONDecodeError:
                        continue
            return snapshots

        return []

    def _window_at_time(self, cv_data: list[dict], t_ms: int,
                        window_substr: str) -> tuple[bool, dict | None]:
        """Check if a window matching substring was visible within tolerance."""
        t_min = t_ms - int(self.tolerance_s * 1000)
        t_max = t_ms + int(self.tolerance_s * 1000)

        for snap in cv_data:
            # Get timestamp from cv watcher format (timestamp_epoch_ms)
            snap_t = snap.get("timestamp_epoch_ms", 0)
            # Or from snapshot format (t_ms)
            if not snap_t:
                snap_t = snap.get("t_ms", 0)

            if not (t_min <= snap_t <= t_max):
                continue  # skip frames outside the window

            # Check interesting_windows (cv watcher format)
            for w in snap.get("interesting_windows", []):
                if window_substr.lower() in w.lower():
                    return True, snap

            # Check windows list (snapshot format)
            for w in snap.get("windows", []):
                w_title = w if isinstance(w, str) else w.get("title", "")
                if window_substr.lower() in w_title.lower():
                    return True, snap

        return False, None

    def check(self) -> dict:
        """Run all assertions and return results."""
        expected = self.load_expected_states()
        if not expected:
            return {"status": "no_data", "message": "No expected states found"}

        cv_data = self.load_cv_data()
        if not cv_data:
            return {"status": "no_data",
                    "message": "No CV/snapshot data found — expected states cannot be verified",
                    "expected_count": len(expected)}

        passed = 0
        failed = 0
        results = []

        for i, exp in enumerate(expected):
            label = exp.get("label", f"assertion_{i}")
            window = exp.get("expected_window", "")
            t_ms = exp.get("t_ms", 0)

            if not window:
                # Assertion without a window expectation — just a checkpoint
                results.append({
                    "label": label,
                    "status": "checkpoint",
                    "message": f"Checkpoint (no window assertion): {label}",
                })
                continue

            found, snap = self._window_at_time(cv_data, t_ms, window)
            if found:
                passed += 1
                results.append({
                    "label": label,
                    "status": "pass",
                    "expected_window": window,
                    "found_at_t_ms": snap.get("timestamp_epoch_ms", snap.get("t_ms", 0)) if snap else 0,
                    "message": f"PASS: '{window}' found within ±{self.tolerance_s}s of t={t_ms}ms",
                })
            else:
                failed += 1
                results.append({
                    "label": label,
                    "status": "fail",
                    "expected_window": window,
                    "t_ms": t_ms,
                    "message": f"FAIL: '{window}' NOT found within ±{self.tolerance_s}s of t={t_ms}ms",
                })

        return {
            "status": "pass" if failed == 0 else "fail",
            "total": len(expected),
            "passed": passed,
            "failed": failed,
            "checkpoints": len(expected) - passed - failed,
            "tolerance_s": self.tolerance_s,
            "results": results,
        }


def main():
    parser = argparse.ArgumentParser(
        description="Post-run expected-state assertion checker")
    parser.add_argument("--session-dir", required=True,
                        help="Path to session directory")
    parser.add_argument("--tolerance", type=float, default=5.0,
                        help="Time tolerance in seconds for window matching")
    args = parser.parse_args()

    if not Path(args.session_dir).is_dir():
        print(f"ERROR: Session dir not found: {args.session_dir}")
        sys.exit(2)

    checker = DemoExpectChecker(args.session_dir, args.tolerance)
    report = checker.check()

    if report["status"] == "no_data":
        print(f"INFO: {report['message']}")
        if report.get("expected_count", 0) > 0:
            print(f"  {report['expected_count']} expected states recorded")
            print("  Run demo with CV watcher enabled to verify")
        sys.exit(2)

    passed = report["passed"]
    failed = report["failed"]
    total = report["total"]

    print("=" * 70)
    print("  EXPECTED-STATE ASSERTIONS")
    print(f"  Session: {args.session_dir}")
    print(f"  Results: {passed} passed, {failed} failed, "
          f"{report['checkpoints']} checkpoints ({total} total)")
    print(f"  Tolerance: ±{report['tolerance_s']}s")
    print()

    for r in report["results"]:
        tag = {"pass": "[PASS]", "fail": "[FAIL]",
               "checkpoint": "[CHKP]"}[r["status"]]
        print(f"  {tag:7s} {r['label']}")
        if r["status"] == "fail":
            print(f"          {r['message']}")

    print()
    if failed > 0:
        print(f"  RESULT: {failed}/{total} assertions FAILED")
        print("=" * 70)
        sys.exit(1)
    else:
        print(f"  RESULT: All {passed} assertions PASSED")
        print("=" * 70)
        sys.exit(0)


if __name__ == "__main__":
    main()
