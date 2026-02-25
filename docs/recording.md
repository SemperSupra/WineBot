# Recording and Annotations

WineBot supports recording session video with automatically generated subtitles and positional annotations.

## Enabling Recording

Recording is opt-in and controlled via environment variables or the `--record` flag in `scripts/run-app.sh`.

### Using the CLI
```bash
./scripts/run-app.sh notepad.exe --record
```

### Using Environment Variables
Set `WINEBOT_RECORD=1` when starting the container.

| Variable | Description | Default |
|----------|-------------|---------|
| `WINEBOT_RECORD` | Enable recording (1 to enable) | 0 |
| `WINEBOT_SESSION_ROOT` | Root directory for session artifacts | `/artifacts/sessions` |
| `WINEBOT_SESSION_LABEL` | Optional label appended to the session ID | (empty) |
| `WINEBOT_USER_DIR` | Override the session user directory (Wine user home) | (empty) |
| `WINEBOT_RECORD_FORMAT` | Video format (currently MKV is canonical) | `mkv` |
| `WINEBOT_RECORDING_STOP_SYNC_WAIT_SECONDS` | Max synchronous API wait before returning `stop_requested` while finalization continues | `3` |

## Sessions and Artifacts

Each WineBot start generates a unique session directory in `/artifacts/sessions/session-<YYYY-MM-DD>-<unix>-<rand>/`.
All captured artifacts (recordings, screenshots, API logs, script outputs) are stored beneath that session directory.

Artifacts produced:
- `video_001.mkv`, `video_002.mkv`, ...: Each start/stop creates a new numbered segment.
- `video_001_part001.mkv`, `video_001_part002.mkv`, ...: Sub‑segments created by pause/resume.
- `segment_001.json`, `segment_002.json`, ...: Per‑segment metadata (start time, fps, resolution).
- `events_001.jsonl`, `events_002.jsonl`, ...: Per‑segment event log.
- `events_001.vtt`, `events_001.ass`, ...: Subtitles/overlays for each segment.
- `parts_001.txt`: Concatenation list for sub‑segments.
- `session.json`: Session‑level metadata (resolution, fps, start time, etc).
- `segment_index.txt`: Next segment number to use.
 - `screenshots/`: Screenshots captured via API or scripts.
 - `logs/`: API, entrypoint, and automation logs.
- `logs/input_events.jsonl`: X11 + agent input trace events (if enabled).
- `logs/input_events_client.jsonl`: noVNC client input trace (if enabled).
- `logs/input_events_windows.jsonl`: Windows-side input trace (if enabled).
- `logs/input_events_network.jsonl`: VNC network input trace (if enabled).
 - `scripts/`: API-generated script files (AHK/AutoIt/Python).
- `user/`: Wine user profile directory (default), used for app inputs/outputs. Can be overridden with `WINEBOT_USER_DIR`.

### Pause/Resume behavior
Pause stops the current sub‑segment quickly; resume starts a new sub‑segment. On stop, sub‑segments are concatenated into `video_###.mkv` and subtitles are generated on the merged timeline.

### Action response semantics
Recording action endpoints return both legacy `status` and normalized convergence fields:
- `result=converged` with `converged=true`: requested state is already reached.
- `result=accepted` with `converged=false`: accepted, still converging asynchronously (for example `stop_requested`, `resume_requested`).

For asynchronous cases, use `GET /health/recording` and wait for the target state (typically `idle` after stop).

## Adding Annotations

You can add annotations to the recording from any script running inside the container using `scripts/annotate.sh`.

### Text Subtitles
```bash
scripts/annotate.sh --text "Step 1: Opening file" --type subtitle
```

### Positional Overlays
Positional overlays appear at specific coordinates on the screen.
```bash
scripts/annotate.sh --text "Click here" --pos "100,200" --type overlay
```
Format for `--pos` is `x,y` or `x,y,w,h`.

## Viewing Overlays

The canonical output is an MKV file. You can toggle the annotations ON/OFF in most video players (VLC, mpv, etc.) by selecting the subtitle track.
- The `Default` track contains basic lifecycle events and text subtitles.
- The `Overlay` track (in ASS format) contains positioned text.

## Input Trace Overlays

If `WINEBOT_INPUT_TRACE_RECORD=1` is set, input trace events (clicks/keys) are injected into the subtitle/overlay tracks with `origin` and `tool` metadata.

## How it Works

1. **Recorder**: A Python module (`automation.recorder`) wraps `ffmpeg` with `x11grab` to capture the X11 display.
2. **Lifecycle Hooks**: `docker/entrypoint.sh` starts the recorder after Xvfb is ready and stops it on exit.
3. **Event Log**: All annotations and lifecycle events are written to `events.jsonl` with monotonic timestamps.
4. **Post-processing**: When the session stops, the recorder generates `.vtt` and `.ass` files from the event log.
