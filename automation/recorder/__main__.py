import argparse
import sys
import os
import json
import time
import signal
import logging
import fcntl
import datetime
import subprocess
import uuid
from collections import deque
from typing import Optional, Any

from .models import SessionManifest, Event
from .ffmpeg import FFMpegRecorder
from .subtitles import SubtitleGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("winebot-recorder")
FFMPEG_PID_FILE = "ffmpeg.pid"
STATE_FILE = "recorder.state"
SEGMENT_FILE = "segment.current"
EVENTS_FILE = "events.current"
PART_INDEX_FILE = "part_index.current"


def get_iso_time():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def lock_file(f):
    fcntl.flock(f, fcntl.LOCK_EX)


def unlock_file(f):
    fcntl.flock(f, fcntl.LOCK_UN)


def append_event(session_dir: str, event: Event, events_path: Optional[str] = None):
    events_path = events_path or os.path.join(session_dir, "events.jsonl")
    with open(events_path, "a") as f:
        lock_file(f)
        try:
            f.write(event.to_json() + "\n")
            f.flush()
        finally:
            unlock_file(f)


def load_events(session_dir: str, events_path: Optional[str] = None):
    events = []
    events_path = events_path or os.path.join(session_dir, "events.jsonl")
    if not os.path.exists(events_path):
        return []

    with open(events_path, "r") as f:
        # No lock needed for reading usually, but to be safe vs partial writes?
        # Appends are atomic enough for jsonl usually.
        for line in f:
            if line.strip():
                try:
                    events.append(Event.from_json(line))
                except json.JSONDecodeError:
                    pass
    return events


def input_recording_enabled() -> bool:
    return os.getenv("WINEBOT_INPUT_TRACE_RECORD", "0") == "1"


def read_manifest_start_epoch_ms(session_dir: str) -> Optional[int]:
    segment_path = os.path.join(session_dir, SEGMENT_FILE)
    manifest_path = None
    try:
        with open(segment_path, "r") as f:
            segment = int(f.read().strip())
        manifest_path = os.path.join(session_dir, f"segment_{segment:03d}.json")
    except Exception:
        manifest_path = None
    if manifest_path and os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r") as f:
                data = json.load(f)
            start_epoch = data.get("start_time_epoch")
            if start_epoch:
                return int(float(start_epoch) * 1000)
        except Exception:
            pass
    session_path = os.path.join(session_dir, "session.json")
    if os.path.exists(session_path):
        try:
            with open(session_path, "r") as f:
                data = json.load(f)
            start_epoch = data.get("start_time_epoch")
            if start_epoch:
                return int(float(start_epoch) * 1000)
        except Exception:
            pass
    return None


def input_log_paths(session_dir: str):
    return [
        ("x11", os.path.join(session_dir, "logs", "input_events.jsonl")),
        ("client", os.path.join(session_dir, "logs", "input_events_client.jsonl")),
        ("windows", os.path.join(session_dir, "logs", "input_events_windows.jsonl")),
        ("network", os.path.join(session_dir, "logs", "input_events_network.jsonl")),
    ]


def should_record_input_event(event: dict) -> bool:
    ev = event.get("event")
    if ev in (
        "button_press",
        "key_press",
        "client_mouse_down",
        "client_key_down",
        "agent_click",
        "mouse_down",
        "key_down",
    ):
        return True
    if ev == "vnc_key":
        return True
    if ev == "vnc_pointer":
        return int(event.get("button_mask", 0)) != 0
    return False


def input_event_message(event: dict) -> str:
    parts = [event.get("event", "input")]
    if event.get("button") is not None:
        parts.append(f"button={event.get('button')}")
    if event.get("button_mask") is not None:
        parts.append(f"mask={event.get('button_mask')}")
    if event.get("key") is not None:
        parts.append(f"key={event.get('key')}")
    if event.get("keycode") is not None:
        parts.append(f"keycode={event.get('keycode')}")
    if event.get("origin"):
        parts.append(f"origin={event.get('origin')}")
    if event.get("tool"):
        parts.append(f"tool={event.get('tool')}")
    return " ".join(parts)


def load_input_trace_events(session_dir: str) -> list:
    if not input_recording_enabled():
        return []

    # Try to find start time from session.json
    start_epoch_ms = None
    session_path = os.path.join(session_dir, "session.json")
    if os.path.exists(session_path):
        try:
            with open(session_path, "r") as f:
                data = json.load(f)
            start_epoch_ms = int(float(data.get("start_time_epoch", 0)) * 1000)
        except Exception:
            pass

    if start_epoch_ms is None:
        return []

    session_id = os.path.basename(session_dir)
    max_events = int(os.getenv("WINEBOT_RECORD_INPUT_MAX_EVENTS", "50000"))
    max_load_mb = int(os.getenv("WINEBOT_MAX_TRACE_LOAD_MB", "100"))
    
    event_buffer: Any
    if max_events > 0:
        event_buffer = deque(maxlen=max_events)
    else:
        event_buffer = [] # type: ignore

    total_loaded_approx_bytes = 0

    for layer, path in input_log_paths(session_dir):
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r") as f:
                for line in f:
                    if not line.strip():
                        continue
                    
                    # Memory Correctness: Stop loading if buffer is getting too large
                    total_loaded_approx_bytes += len(line)
                    if total_loaded_approx_bytes > (max_load_mb * 1024 * 1024):
                        logger.warning(f"Trace buffer limit reached ({max_load_mb}MB). Skipping remaining events.")
                        break

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not should_record_input_event(data):
                        continue

                    # Try canonical field first, then fallback
                    t_epoch = data.get("t_wall_ms") or data.get("timestamp_epoch_ms")
                    if t_epoch is None:
                        continue

                    t_epoch = int(t_epoch)
                    t_rel = max(0, t_epoch - start_epoch_ms)
                    pos = None
                    if data.get("x") is not None and data.get("y") is not None:
                        pos = {"x": data.get("x"), "y": data.get("y")}
                    msg = input_event_message(data)
                    event_buffer.append(
                        Event(
                            session_id=session_id,
                            t_rel_ms=t_rel,
                            t_epoch_ms=t_epoch,
                            level="INFO",
                            kind="input",
                            message=msg,
                            pos=pos,
                            tags=["input", layer],
                            source=layer,
                            extra=data,
                        )
                    )
        except Exception:
            continue
    return list(event_buffer)


def read_pid(path: str) -> Optional[int]:
    try:
        with open(path, "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def write_state(session_dir: str, state: str):
    try:
        with open(os.path.join(session_dir, STATE_FILE), "w") as f:
            f.write(state)
    except Exception:
        pass


def signal_ffmpeg(session_dir: str, sig: int, action: str):
    pid_path = os.path.join(session_dir, FFMPEG_PID_FILE)
    pid = read_pid(pid_path)
    if not pid:
        logger.error(f"No ffmpeg PID file found at {pid_path}.")
        sys.exit(1)
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        logger.error(f"ffmpeg process {pid} not found.")
        sys.exit(1)

    manifest = load_manifest(session_dir)
    events_path = read_current_events_path(session_dir)
    if manifest:
        try:
            start_time_epoch = manifest["start_time_epoch"]
            now_epoch = time.time() * 1000
            t_rel = int(now_epoch - start_time_epoch)
            append_event(
                session_dir,
                Event(
                    session_id=manifest["session_id"],
                    t_rel_ms=t_rel,
                    t_epoch_ms=int(now_epoch),
                    level="INFO",
                    kind=f"recorder_{action}",
                    message=f"Recorder {action}",
                ),
                events_path=events_path,
            )
        except Exception:
            pass

    write_state(session_dir, "paused" if action == "pause" else "recording")


def read_current_events_path(session_dir: str) -> Optional[str]:
    path = os.path.join(session_dir, EVENTS_FILE)
    try:
        with open(path, "r") as f:
            value = f.read().strip()
        return value or None
    except Exception:
        return None


def read_current_segment(session_dir: str) -> Optional[int]:
    path = os.path.join(session_dir, SEGMENT_FILE)
    try:
        with open(path, "r") as f:
            return int(f.read().strip())
    except Exception:
        return None


def segment_paths(session_dir: str, segment: Optional[int]):
    if segment is None:
        output_file = os.path.join(session_dir, "video.mkv")
        events_path = os.path.join(session_dir, "events.jsonl")
        vtt_path = os.path.join(session_dir, "events.vtt")
        ass_path = os.path.join(session_dir, "events.ass")
        segment_manifest = os.path.join(session_dir, "session.json")
        return output_file, events_path, vtt_path, ass_path, segment_manifest
    suffix = f"{segment:03d}"
    output_file = os.path.join(session_dir, f"video_{suffix}.mkv")
    events_path = os.path.join(session_dir, f"events_{suffix}.jsonl")
    vtt_path = os.path.join(session_dir, f"events_{suffix}.vtt")
    ass_path = os.path.join(session_dir, f"events_{suffix}.ass")
    segment_manifest = os.path.join(session_dir, f"segment_{suffix}.json")
    return output_file, events_path, vtt_path, ass_path, segment_manifest


def load_manifest(session_dir: str) -> Optional[dict]:
    seg = read_current_segment(session_dir)
    manifest_path = None
    if seg is not None:
        _, _, _, _, manifest_path = segment_paths(session_dir, seg)
    if manifest_path and os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r") as f:
                return json.load(f)
        except Exception:
            return None
    session_path = os.path.join(session_dir, "session.json")
    if os.path.exists(session_path):
        try:
            with open(session_path, "r") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def parts_file_path(session_dir: str, segment: int) -> str:
    return os.path.join(session_dir, f"parts_{segment:03d}.txt")


def part_index_path(session_dir: str, segment: int) -> str:
    return os.path.join(session_dir, f"part_index_{segment:03d}.txt")


def next_part_index(session_dir: str, segment: int) -> int:
    path = part_index_path(session_dir, segment)
    current = None
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                current = int(f.read().strip())
        except Exception:
            current = None
    if current is None:
        current = 1
    next_value = current + 1
    try:
        with open(path, "w") as f:
            f.write(str(next_value))
    except Exception:
        pass
    return current


def append_part(parts_file: str, part_path: str):
    with open(parts_file, "a") as f:
        f.write(f"file '{part_path}'\n")


def concat_parts(parts_file: str, output_file: str) -> bool:
    if not os.path.exists(parts_file):
        return False
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        parts_file,
        "-c",
        "copy",
        output_file,
    ]
    logger.info(f"Concatenating parts: {' '.join(cmd)}")
    try:
        subprocess.run(
            cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to concat parts: {e.stderr.decode()}")
        return False


def adjust_events_for_pauses(events):
    pauses = []
    pause_start = None
    for event in events:
        if event.kind == "recorder_pause":
            pause_start = event.t_epoch_ms
        elif event.kind == "recorder_resume" and pause_start is not None:
            pauses.append((pause_start, event.t_epoch_ms))
            pause_start = None

    if not pauses:
        return events

    adjusted = []
    for event in events:
        offset = 0
        for start, end in pauses:
            if event.t_epoch_ms >= end:
                offset += end - start
            elif event.t_epoch_ms >= start:
                offset += event.t_epoch_ms - start
        new_event = Event(
            session_id=event.session_id,
            t_rel_ms=max(0, event.t_rel_ms - offset),
            t_epoch_ms=event.t_epoch_ms,
            level=event.level,
            kind=event.kind,
            message=event.message,
            pos=event.pos,
            style=event.style,
            tags=event.tags,
            source=event.source,
            extra=event.extra,
            schema_version=event.schema_version,
        )
        adjusted.append(new_event)
    return adjusted


def cmd_start(args):
    session_dir = args.session_dir
    os.makedirs(session_dir, exist_ok=True)

    # Write PID file
    pid_file = os.path.join(session_dir, "recorder.pid")
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))

    start_time_monotonic = time.monotonic() * 1000
    start_time_epoch = time.time() * 1000

    # Write session manifest if missing
    session_manifest_path = os.path.join(session_dir, "session.json")
    if not os.path.exists(session_manifest_path):
        manifest = SessionManifest(
            session_id=os.path.basename(session_dir),
            recording_timeline_id=f"timeline-{uuid.uuid4().hex}",
            start_time_epoch=start_time_epoch,
            start_time_iso=get_iso_time(),
            hostname=os.uname().nodename,
            display=args.display,
            resolution=args.resolution,
            fps=args.fps,
            git_sha=os.environ.get("GIT_SHA"),  # Optional
        )
        with open(session_manifest_path, "w") as f:
            f.write(manifest.to_json())
    else:
        with open(session_manifest_path, "r") as f:
            manifest = SessionManifest.from_json(f.read())

    segment = args.segment
    output_file, events_path, vtt_path, ass_path, segment_manifest_path = segment_paths(
        session_dir, segment
    )
    parts_file = None
    part_index = None
    if segment is not None:
        parts_file = parts_file_path(session_dir, segment)
        segment_manifest = {
            "schema_version": manifest.schema_version,
            "session_id": manifest.session_id,
            "recording_timeline_id": manifest.recording_timeline_id,
            "segment": segment,
            "start_time_epoch": start_time_epoch,
            "start_time_iso": get_iso_time(),
            "hostname": manifest.hostname,
            "display": args.display,
            "resolution": args.resolution,
            "fps": args.fps,
            "git_sha": manifest.git_sha,
        }
        with open(segment_manifest_path, "w") as f:
            json.dump(segment_manifest, f)
        with open(os.path.join(session_dir, SEGMENT_FILE), "w") as f:
            f.write(str(segment))
        with open(os.path.join(session_dir, EVENTS_FILE), "w") as f:
            f.write(events_path)
        with open(os.path.join(session_dir, PART_INDEX_FILE), "w") as f:
            f.write(str(segment))

    # Start FFMpeg (part-based to enable fast pause/resume)
    paused = False
    recorder = None

    def start_part():
        nonlocal recorder, part_index, output_file
        if segment is not None:
            part_index = next_part_index(session_dir, segment)
            output_file = os.path.join(
                session_dir, f"video_{segment:03d}_part{part_index:03d}.mkv"
            )
            if parts_file:
                append_part(parts_file, output_file)

        meta = {
            "title": manifest.session_id,
            "encoder": "WineBot Recorder",
            "creation_time": get_iso_time(),
            "WINEBOT_SESSION_ID": manifest.session_id,
            "WINEBOT_GIT_SHA": manifest.git_sha,
            "WINEBOT_HOSTNAME": manifest.hostname,
            "WINEBOT_DISPLAY": manifest.display,
        }

        recorder = FFMpegRecorder(args.display, args.resolution, args.fps, output_file)
        recorder.start(metadata=meta)
        if recorder.process and recorder.process.pid:
            with open(os.path.join(session_dir, FFMPEG_PID_FILE), "w") as f:
                f.write(str(recorder.process.pid))
        write_state(session_dir, "recording")

    def stop_part():
        nonlocal recorder
        if recorder:
            recorder.stop()
        ffmpeg_pid_path = os.path.join(session_dir, FFMPEG_PID_FILE)
        if os.path.exists(ffmpeg_pid_path):
            os.remove(ffmpeg_pid_path)

    start_part()

    # Log start event
    append_event(
        session_dir,
        Event(
            session_id=manifest.session_id,
            t_rel_ms=0,
            t_epoch_ms=int(start_time_epoch),
            level="INFO",
            kind="lifecycle",
            message="Session started",
        ),
        events_path=events_path,
    )

    append_event(
        session_dir,
        Event(
            session_id=manifest.session_id,
            t_rel_ms=0,
            t_epoch_ms=int(start_time_epoch),
            level="INFO",
            kind="recorder_start",
            message="Recorder started",
        ),
        events_path=events_path,
    )

    def cleanup(signum, frame):
        nonlocal paused
        logger.info("Received stop signal. Cleaning up...")
        end_time_monotonic = time.monotonic() * 1000
        t_rel = int(end_time_monotonic - start_time_monotonic)
        t_epoch = int(time.time() * 1000)

        append_event(
            session_dir,
            Event(
                session_id=manifest.session_id,
                t_rel_ms=t_rel,
                t_epoch_ms=t_epoch,
                level="INFO",
                kind="recorder_stop",
                message="Recorder stopped",
            ),
            events_path=events_path,
        )

        if not paused:
            stop_part()

        # Generate Subtitles
        logger.info("Generating subtitles...")
        events = load_events(session_dir, events_path=events_path)
        events = adjust_events_for_pauses(events)
        input_events = load_input_trace_events(session_dir)
        if input_events:
            events.extend(input_events)
            events.sort(key=lambda e: e.t_rel_ms)
        gen = SubtitleGenerator(events)

        with open(vtt_path, "w") as f:
            f.write(gen.generate_vtt())

        # Parse resolution for ASS
        w, h = map(int, args.resolution.split("x"))
        with open(ass_path, "w") as f:
            f.write(gen.generate_ass(w, h))

        # Mux into video with global metadata
        meta = {
            "title": manifest.session_id,
            "encoder": "WineBot Recorder",
            "creation_time": get_iso_time(),
            "WINEBOT_SESSION_ID": manifest.session_id,
            "WINEBOT_GIT_SHA": manifest.git_sha,
            "WINEBOT_HOSTNAME": manifest.hostname,
            "WINEBOT_DISPLAY": manifest.display,
        }
        final_output = output_file
        if segment is not None:
            final_output = os.path.join(session_dir, f"video_{segment:03d}.mkv")
            if parts_file and os.path.exists(parts_file):
                concat_parts(parts_file, final_output)
        muxer = FFMpegRecorder(args.display, args.resolution, args.fps, final_output)
        muxer.mux_subtitles(ass_path, vtt_path, metadata=meta)

        # Remove PID file
        if os.path.exists(pid_file):
            os.remove(pid_file)
        ffmpeg_pid_path = os.path.join(session_dir, FFMPEG_PID_FILE)
        if os.path.exists(ffmpeg_pid_path):
            os.remove(ffmpeg_pid_path)
        state_path = os.path.join(session_dir, STATE_FILE)
        if os.path.exists(state_path):
            os.remove(state_path)
        if os.path.exists(os.path.join(session_dir, SEGMENT_FILE)):
            os.remove(os.path.join(session_dir, SEGMENT_FILE))
        if os.path.exists(os.path.join(session_dir, EVENTS_FILE)):
            os.remove(os.path.join(session_dir, EVENTS_FILE))
        if os.path.exists(os.path.join(session_dir, PART_INDEX_FILE)):
            os.remove(os.path.join(session_dir, PART_INDEX_FILE))

        sys.exit(0)

    def handle_pause(signum, frame):
        nonlocal paused
        if paused:
            return
        stop_part()
        append_event(
            session_dir,
            Event(
                session_id=manifest.session_id,
                t_rel_ms=int(time.monotonic() * 1000 - start_time_monotonic),
                t_epoch_ms=int(time.time() * 1000),
                level="INFO",
                kind="recorder_pause",
                message="Recorder pause",
            ),
            events_path=events_path,
        )
        write_state(session_dir, "paused")
        paused = True

    def handle_resume(signum, frame):
        nonlocal paused
        if not paused:
            return
        start_part()
        append_event(
            session_dir,
            Event(
                session_id=manifest.session_id,
                t_rel_ms=int(time.monotonic() * 1000 - start_time_monotonic),
                t_epoch_ms=int(time.time() * 1000),
                level="INFO",
                kind="recorder_resume",
                message="Recorder resume",
            ),
            events_path=events_path,
        )
        paused = False

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGUSR1, handle_pause)
    signal.signal(signal.SIGUSR2, handle_resume)

    logger.info("Recording active. Waiting for signal...")
    while True:
        time.sleep(1)


def cmd_stop(args):
    session_dir = args.session_dir
    pid_file = os.path.join(session_dir, "recorder.pid")

    if not os.path.exists(pid_file):
        logger.error(f"No PID file found at {pid_file}. Is recorder running?")
        sys.exit(1)

    with open(pid_file, "r") as f:
        pid = int(f.read().strip())

    try:
        os.kill(pid, signal.SIGTERM)
        logger.info(f"Sent SIGTERM to recorder process {pid}")
    except ProcessLookupError:
        logger.warning(f"Process {pid} not found. Cleaning up artifacts anyway?")
        # Force generation if process died?
        # For now, just exit. The recorder process logic handles generation on exit.
        # If it crashed hard, we might need a 'recover' command.

    # Wait for it to vanish
    for _ in range(10):
        if not os.path.exists(pid_file):
            logger.info("Recorder stopped successfully.")
            break
        time.sleep(0.5)
    else:
        logger.warning("Recorder PID file still exists after 5s.")


def cmd_annotate(args):
    session_dir = args.session_dir
    manifest = load_manifest(session_dir)
    if not manifest:
        logger.error("Session manifest not found.")
        sys.exit(1)
    start_time_epoch = manifest["start_time_epoch"]
    now_epoch = time.time() * 1000
    t_rel = int(now_epoch - start_time_epoch)

    pos = None
    if args.pos:
        parts = list(map(int, args.pos.split(",")))
        if len(parts) == 4:
            pos = {"x": parts[0], "y": parts[1], "w": parts[2], "h": parts[3]}
        elif len(parts) == 2:
            pos = {"x": parts[0], "y": parts[1], "w": 0, "h": 0}

    style = None
    if args.style:
        try:
            style = json.loads(args.style)
        except Exception:
            style = {"raw": args.style}

    event = Event(
        session_id=manifest["session_id"],
        t_rel_ms=t_rel,
        t_epoch_ms=int(now_epoch),
        level="INFO",
        kind=args.kind,  # annotation, lifecycle, etc.
        message=args.text,
        pos=pos,
        style=style,
        source=args.source,
    )

    append_event(session_dir, event, events_path=read_current_events_path(session_dir))


def cmd_pause(args):
    pid = read_pid(os.path.join(args.session_dir, "recorder.pid"))
    if not pid:
        logger.error("Recorder PID not found.")
        sys.exit(1)
    try:
        os.kill(pid, signal.SIGUSR1)
    except ProcessLookupError:
        logger.error("Recorder process not found.")
        sys.exit(1)


def cmd_resume(args):
    pid = read_pid(os.path.join(args.session_dir, "recorder.pid"))
    if not pid:
        logger.error("Recorder PID not found.")
        sys.exit(1)
    try:
        os.kill(pid, signal.SIGUSR2)
    except ProcessLookupError:
        logger.error("Recorder process not found.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(prog="winebot_recorder")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Start
    p_start = subparsers.add_parser("start")
    p_start.add_argument("--session-dir", required=True)
    p_start.add_argument("--display", default=":99")
    p_start.add_argument("--resolution", default="1920x1080")
    p_start.add_argument("--fps", type=int, default=30)
    p_start.add_argument("--segment", type=int, default=None)

    # Stop
    p_stop = subparsers.add_parser("stop")
    p_stop.add_argument("--session-dir", required=True)

    # Annotate
    p_ann = subparsers.add_parser("annotate")
    p_ann.add_argument("--session-dir", required=True)
    p_ann.add_argument("--text", required=True)
    p_ann.add_argument("--kind", default="annotation")
    p_ann.add_argument("--pos", help="x,y,w,h or x,y")
    p_ann.add_argument("--style", help="JSON style string")
    p_ann.add_argument("--source", help="Source tool name")

    # Pause
    p_pause = subparsers.add_parser("pause")
    p_pause.add_argument("--session-dir", required=True)

    # Resume
    p_resume = subparsers.add_parser("resume")
    p_resume.add_argument("--session-dir", required=True)

    args = parser.parse_args()

    if args.command == "start":
        cmd_start(args)
    elif args.command == "stop":
        cmd_stop(args)
    elif args.command == "annotate":
        cmd_annotate(args)
    elif args.command == "pause":
        cmd_pause(args)
    elif args.command == "resume":
        cmd_resume(args)


if __name__ == "__main__":
    main()
