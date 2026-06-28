#!/usr/bin/env python3
# EXECUTION: HOST — reads session JSONL files from artifacts/; pure data processing
# STATUS: ACTIVE — unified timeline merger for all four data layers (recording+API+CV+trace)
"""Unified timeline merger for WineBot session data.

Merges all four data layers into a single timestamp-sorted JSONL file:
  - recording  — annotation/chapter events from events_001.jsonl
  - api        — input/key, input/mouse calls from logs/input_events*.jsonl
  - cv         — watcher frames from watcher.jsonl (if present)
  - input_trace — X11/AHK keyboard events from logs/input_events*.jsonl

Usage:
  python3 scripts/diagnostics/merge-timeline.py --session-dir /sessions/session-abc123
  # Output: <session-dir>/analysis/timeline.jsonl
"""

import argparse
import json
import sys
from pathlib import Path


class TimelineMerger:
    """Merges multiple event sources into a unified timeline."""

    def __init__(self, session_dir: str):
        self.session_dir = Path(session_dir)
        self.out_dir = self.session_dir / "analysis"
        self.out_dir.mkdir(exist_ok=True)

        # Load session manifest for start time
        self.manifest = self._load_manifest()
        self.start_epoch = float(self.manifest.get("start_time_epoch", 0))

    def _load_manifest(self) -> dict:
        path = self.session_dir / "session.json"
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return {}

    def _read_jsonl(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        events = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return events

    def _time_ms(self, event: dict) -> float | None:
        """Extract relative time in ms from an event."""
        # Standard event format
        if "t_rel_ms" in event:
            return float(event["t_rel_ms"])

        # Watcher format: has index and timestamp_epoch_ms
        if "timestamp_epoch_ms" in event and self.start_epoch > 0:
            return (float(event["timestamp_epoch_ms"]) - self.start_epoch)

        # Input trace format: has timestamp_epoch_ms
        if "ts_epoch_ms" in event and self.start_epoch > 0:
            return (float(event["ts_epoch_ms"]) - self.start_epoch)

        return None

    def _normalize_recording_event(self, event: dict) -> dict | None:
        """Convert recording event to unified format."""
        if event.get("event") == "snapshot":
            return None  # cv-watcher events handled separately

        kind = event.get("kind", event.get("event", "unknown"))
        t_rel = self._time_ms(event)
        if t_rel is None:
            return None

        return {
            "t_rel_ms": round(t_rel, 1),
            "source": "recording",
            "kind": kind,
            "text": event.get("message", event.get("text", "")),
            "tags": event.get("tags", []),
            "extra": event.get("extra", {}),
        }

    def _normalize_api_event(self, event: dict) -> dict | None:
        """Convert API/input event to unified format."""
        # API events have: event, phase, tool, timestamp_epoch_ms, trace_id
        # Trace events have: type, layer, timestamp_epoch_ms
        ts_epoch = event.get("timestamp_epoch_ms", 0)
        if ts_epoch and self.start_epoch > 0:
            # session.json start_time_epoch is in milliseconds (same unit as timestamp_epoch_ms)
            t_rel = (float(ts_epoch) - self.start_epoch)
        else:
            t_rel = self._time_ms(event)
        if t_rel is None:
            return None

        # Determine event type and kind
        evt_type = event.get("event", event.get("type", "unknown"))
        phase = event.get("phase", "")
        tool = event.get("tool", "")
        layer = event.get("layer", event.get("source", ""))

        return {
            "t_rel_ms": round(t_rel, 1),
            "source": "api",
            "kind": evt_type,
            "phase": phase,
            "tool": tool,
            "layer": layer,
            "trace_id": event.get("trace_id", ""),
            "status": event.get("status", ""),
            "text": event.get("keys", event.get("key", event.get("text", ""))),
            "extra": {k: v for k, v in event.items()
                      if k not in ("t_rel_ms", "event", "type", "phase", "tool",
                                   "layer", "source", "trace_id", "status",
                                   "keys", "key", "text", "timestamp_epoch_ms",
                                   "timestamp_utc", "session_id", "schema_version",
                                   "t_wall_ms", "t_mono_ms", "event_id", "seq")},
        }

    def _normalize_cv_event(self, snapshot: dict) -> dict | None:
        """Convert CV watcher snapshot to unified format."""
        if snapshot.get("event") != "snapshot":
            return None

        t_rel = self._time_ms(snapshot)
        if t_rel is None:
            return None

        interesting = snapshot.get("interesting_windows", [])
        return {
            "t_rel_ms": round(t_rel, 1),
            "source": "cv",
            "kind": "snapshot",
            "text": f"Δ={snapshot.get('pixels_changed', 0)}px",
            "windows": interesting,
            "windows_count": snapshot.get("windows_count", 0),
            "index": snapshot.get("index", 0),
        }

    def _normalize_trace_event(self, event: dict) -> dict | None:
        """Convert input trace event to unified format."""
        ts_epoch = event.get("timestamp_epoch_ms", 0)
        if ts_epoch and self.start_epoch > 0:
            t_rel = (float(ts_epoch) - self.start_epoch)
        else:
            t_rel = self._time_ms(event)
        if t_rel is None:
            return None

        layer = event.get("layer", event.get("source_layer", "unknown"))
        return {
            "t_rel_ms": round(t_rel, 1),
            "source": "input_trace",
            "kind": event.get("type", event.get("event", "unknown")),
            "layer": layer,
            "text": event.get("key", event.get("text", event.get("keys", ""))),
            "vk": event.get("vk", event.get("detail", event.get("virtual_key", ""))),
            "tool": event.get("tool", event.get("origin", "")),
            "trace_id": event.get("trace_id", ""),
            "extra": {k: v for k, v in event.items()
                      if k not in ("t_rel_ms", "type", "event", "layer", "source",
                                   "key", "text", "keys", "vk", "detail",
                                   "virtual_key", "tool", "origin", "trace_id",
                                   "timestamp_epoch_ms", "timestamp_utc",
                                   "session_id", "schema_version", "event_id",
                                   "seq", "t_wall_ms", "t_mono_ms", "device",
                                   "modifiers", "button", "x", "y", "xi2_type",
                                   "xi2_raw")},
        }

    def merge(self) -> str:
        """Merge all sources and write timeline.jsonl."""
        timeline: list[dict] = []

        # 1. Recording events
        recording_events = self._read_jsonl(self.session_dir / "events_001.jsonl")
        for e in recording_events:
            norm = self._normalize_recording_event(e)
            if norm:
                timeline.append(norm)
        print(f"  Recording events: {len(timeline)}")

        # 2. API / input events from logs
        api_count = 0
        for log_dir in (self.session_dir / "logs").glob("input_events*.jsonl"):
            for e in self._read_jsonl(log_dir):
                norm = self._normalize_api_event(e)
                if norm:
                    timeline.append(norm)
                    api_count += 1
        print(f"  API/input events: {api_count}")

        # 3. CV watcher (may be in /tmp or analysis dir)
        cv_count = 0
        for watcher_path in [
            Path("/tmp/winebot_watcher/watcher.jsonl"),
            self.session_dir / "watcher.jsonl",
            self.out_dir.parent / "watcher.jsonl",
        ]:
            for snap in self._read_jsonl(watcher_path):
                norm = self._normalize_cv_event(snap)
                if norm:
                    timeline.append(norm)
                    cv_count += 1
        if cv_count:
            print(f"  CV watcher frames: {cv_count}")

        # 4. Input trace layers
        trace_count = 0
        if (self.session_dir / "logs").exists():
            for trace_file in sorted((self.session_dir / "logs").glob("input_*_trace*.jsonl")):
                for e in self._read_jsonl(trace_file):
                    norm = self._normalize_trace_event(e)
                    if norm:
                        timeline.append(norm)
                        trace_count += 1
        if trace_count:
            print(f"  Input trace events: {trace_count}")

        # 5. CV element detection (from analysis, if present)
        cv_elem_count = 0
        elements_path = self.out_dir / "elements.jsonl"
        if elements_path.exists():
            for e in self._read_jsonl(elements_path):
                t = e.get("timestamp_s", 0) * 1000  # convert to ms
                text_summary = e.get("text_summary", [])
                timeline.append({
                    "t_rel_ms": round(t, 1),
                    "source": "cv_elements",
                    "kind": "frame_analysis",
                    "text": ", ".join(text_summary[:8]) if text_summary else "",
                    "click_targets": e.get("click_targets", {}),
                    "yolo_objects": len(e.get("elements", {}).get("yolo_objects", [])),
                    "ocr_regions": len(e.get("elements", {}).get("text_regions", [])),
                })
                cv_elem_count += 1
        if cv_elem_count:
            print(f"  CV element frames: {cv_elem_count}")

        # Sort by time
        timeline.sort(key=lambda x: x["t_rel_ms"])

        # Write
        output_path = self.out_dir / "timeline.jsonl"
        with open(output_path, "w") as f:
            for entry in timeline:
                f.write(json.dumps(entry) + "\n")

        total = len(timeline)
        print(f"\n  Total timeline entries: {total}")
        print(f"  Output: {output_path}")

        # Print summary stats
        sources = {}
        kinds = {}
        for e in timeline:
            s = e["source"]
            sources[s] = sources.get(s, 0) + 1
            k = f"{s}:{e['kind']}"
            kinds[k] = kinds.get(k, 0) + 1

        print("\n  By source:")
        for s, c in sorted(sources.items()):
            print(f"    {s}: {c}")
        print("\n  By kind (top 15):")
        for k, c in sorted(kinds.items(), key=lambda x: -x[1])[:15]:
            print(f"    {k}: {c}")

        return str(output_path)


def main():
    parser = argparse.ArgumentParser(
        description="Merge WineBot session logs into unified timeline")
    parser.add_argument("--session-dir", required=True,
                        help="Path to session directory")
    args = parser.parse_args()

    if not Path(args.session_dir).is_dir():
        print(f"ERROR: Session dir not found: {args.session_dir}")
        sys.exit(1)

    print(f"Timeline Merger — {args.session_dir}\n")
    merger = TimelineMerger(args.session_dir)
    output = merger.merge()

    print(f"\nDone: {output}")
    print(f"Query with: jq '.[] | select(.t_rel_ms >= 40000 and .t_rel_ms <= 50000)' {output}")


if __name__ == "__main__":
    main()
