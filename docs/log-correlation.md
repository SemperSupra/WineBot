# Log Correlation — Video + API + Trace + CV

## Current Correlation Layers

WineBot generates four independent data streams during a session.
They share a common session ID and timestamp but are not linked at query time.

| Layer | Source | Container | Storage | Query Method |
|:---|:---|:---|:---|:---|
| **Video** | WineBot Recorder | `video_001.mkv` | Session dir | VLC/MPV player |
| **Annotations** | `python3 -m automation.recorder annotate` | `events_001.jsonl` → `events_001.vtt` | Session dir | Subtitles in video |
| **Input Trace** | `/input/events` API endpoint | `logs/input_events*.jsonl` | Session logs | `GET /input/events?source=&limit=200` |
| **CV Watcher** | `cv-watcher.py` | `watcher.jsonl` | /tmp/winebot_watcher | `cv-analyze.py` |

## The Correlation Gap

**No single query answers: "What was happening at 45 seconds into the video?"**

To answer that today, you need to:
1. Convert video timestamp (45s) to wall clock (video_start + 45s)
2. Find the nearest recording annotation event by `t_rel_ms ≈ 45000`
3. Query input traces for that time window
4. (If CV was running) find the nearest watcher frame

## Proposed: Unified Timeline Index

A single `timeline.jsonl` that merges all four layers by timestamp:

```jsonl
{"t_rel_ms": 45145, "source": "recording", "event": "chapter", "text": "Part 2: AHK Pipe Dialog"}
{"t_rel_ms": 46200, "source": "api", "event": "agent_key", "keys": "Hello", "backend": "ahk", "trace_id": "abc123"}
{"t_rel_ms": 46500, "source": "api", "event": "agent_key", "phase": "complete", "status": "sent"}
{"t_rel_ms": 47100, "source": "cv", "event": "window_appeared", "window": "WineBot Save Dialog"}
{"t_rel_ms": 47300, "source": "cv", "event": "element_found", "label": "Save", "bbox": [100, 80, 100, 30]}
{"t_rel_ms": 47500, "source": "input_trace", "event": "key_down", "vk": "vk41", "trace_id": "abc123"}
{"t_rel_ms": 48100, "source": "recording", "event": "annotation", "text": "FILE SAVED"}
```

This enables queries like:
- "Show me every API call and its trace evidence between 45s-50s"
- "What was on screen when the error appeared at 87s?"
- "Did the Save button appear within 2s of the Ctrl+S API call?"

## Implementation

### Phase 1: Timeline Merge Script

`scripts/diagnostics/merge-timeline.py`:

```bash
python3 scripts/diagnostics/merge-timeline.py --session-dir /sessions/session-abc123
# Output: <session-dir>/analysis/timeline.jsonl
```

Reads all four sources and merges into a single timestamp-sorted JSONL file.

### Phase 2: Timeline Viewer

Add a `GET /sessions/{id}/timeline` API endpoint that returns the merged timeline
for a given time range, filterable by source and event type.

### Phase 3: Video-Annotation Sync

During recording, input trace events and CV watcher frames are time-stamped.
The merge script aligns them to the video via the recording's `start_time_epoch`.

## Current File Inventory Per Session

```
session-2026-06-21-abc123/
├── video_001.mkv                     # Recording video
├── video_001_part001.mkv             # Segment 1
├── video_001_part002.mkv             # Segment 2
├── events_001.jsonl                  # Annotation events (kind=annotation|chapter|recorder_start)
├── events_001.vtt                    # Subtitle track (WebVTT)
├── events_001.ass                    # Subtitle track (ASS)
├── session.json                      # Session manifest (start_time_epoch, resolution, etc.)
├── recording_artifacts_manifest.json # Recording artifact index
├── segment_001.json                  # Segment manifest
├── logs/
│   ├── api.log                       # Uvicorn API log (stdout)
│   ├── explorer.log                  # Desktop supervisor log
│   ├── input_events.jsonl            # XI2 input trace events (x11 layer)
│   ├── input_events_client.jsonl     # noVNC client trace (client layer)
│   ├── input_events_network.jsonl    # VNC proxy trace (network layer)
│   ├── input_events_windows.jsonl    # AHK hook trace (windows layer)
│   ├── input_events_x11_core.jsonl   # xinput test events (x11 core layer)
│   ├── input_trace.log               # Input trace stderr
│   └── diagnostics/
│       └── input_trace_bisect.log    # Diagnostic bisect output
└── analysis/                          # (post-recording, not yet committed)
    ├── timeline.jsonl                # Merged timeline
    ├── elements.jsonl                # CV element detection per frame
    ├── enriched_events.jsonl         # Events + CV position data
    ├── summary.json                  # Analysis summary
    └── frames/                       # Extracted frames from video
```

## Correlation IDs

| ID | Scope | Present In |
|:---|:---|:---|
| `session_id` | Global | All logs, events, traces |
| `trace_id` | Per API input call | API events, input trace, Windows trace |
| `recording_timeline_id` | Per recording session | Recording manifest, events |
| `operation_id` | Per recording action | recording/stop response |
