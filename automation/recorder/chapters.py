"""FFmpeg chapter metadata generation from recording annotation events.

Events with kind="chapter" are converted to FFmpeg's ffmetadata format
and embedded into the MKV video container alongside subtitles.
"""

import os
import json
from typing import List, Optional

from .models import Event


def generate_chapter_file(
    session_dir: str,
    output_path: Optional[str] = None,
    title: Optional[str] = None,
) -> Optional[str]:
    """Read annotation events and write an ffmetadata chapter file.

    Events with kind="chapter" become CHAPTER blocks. If no chapter events
    exist, returns None (no file is created).

    Returns the path to the chapter file, or None.
    """
    events = _read_events(session_dir)
    chapter_events = [e for e in events if e.get("kind") == "chapter"]

    if not chapter_events:
        return None

    output_path = output_path or os.path.join(session_dir, "chapters.ffmetadata.txt")
    lines = [";FFMETADATA1"]

    if title:
        lines.append(f"title={title}")

    total_chapters = len(chapter_events)
    for i, evt in enumerate(chapter_events):
        t_start_ms = int(evt["t_rel_ms"])
        title_text = evt.get("message", f"Chapter {i + 1}")

        # Duration: until next chapter, or +30s if last
        if i < total_chapters - 1:
            t_end_ms = int(chapter_events[i + 1]["t_rel_ms"])
        else:
            t_end_ms = t_start_ms + 30000

        lines.append("[CHAPTER]")
        lines.append("TIMEBASE=1/1000")
        lines.append(f"START={t_start_ms}")
        lines.append(f"END={t_end_ms}")
        lines.append(f"title={title_text}")

    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    return output_path


def _read_events(session_dir: str) -> List[dict]:
    """Read all events from the events JSONL file."""
    events_path = os.path.join(session_dir, "events.jsonl")
    if not os.path.exists(events_path):
        # Try alternative paths
        alt_path = os.path.join(session_dir, "events_001.jsonl")
        if os.path.exists(alt_path):
            events_path = alt_path
        else:
            return []

    items: List[dict] = []
    with open(events_path, "r") as f:
        for line in f:
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items
