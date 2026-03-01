import json
from pathlib import Path

from api.utils.files import (
    ensure_recording_timeline_id,
    enforce_recording_retention,
    write_recording_artifact_manifest,
    write_session_manifest,
)


def test_recording_artifact_manifest_contains_timeline_and_artifacts(tmp_path: Path):
    session_dir = tmp_path / "session-1"
    logs_dir = session_dir / "logs"
    logs_dir.mkdir(parents=True)
    write_session_manifest(str(session_dir), "session-1")

    (session_dir / "video_001.mkv").write_bytes(b"video-bytes")
    (session_dir / "events_001.jsonl").write_text('{"kind":"lifecycle"}\n', encoding="utf-8")
    (logs_dir / "input_events.jsonl").write_text('{"event":"click"}\n', encoding="utf-8")

    timeline_id = ensure_recording_timeline_id(str(session_dir))
    output_path = write_recording_artifact_manifest(
        str(session_dir), generated_by_action="start"
    )

    assert output_path is not None
    payload = json.loads(Path(output_path).read_text(encoding="utf-8"))
    assert payload["manifest_type"] == "recording_artifacts"
    assert payload["recording_timeline_id"] == timeline_id
    assert payload["generated_by_action"] == "start"

    artifact_paths = {item["path"] for item in payload["artifacts"]}
    assert "video_001.mkv" in artifact_paths
    assert "events_001.jsonl" in artifact_paths
    assert "logs/input_events.jsonl" in artifact_paths


def test_recording_artifact_manifest_can_exclude_input_trace(tmp_path: Path, monkeypatch):
    session_dir = tmp_path / "session-2"
    logs_dir = session_dir / "logs"
    logs_dir.mkdir(parents=True)
    write_session_manifest(str(session_dir), "session-2")
    (session_dir / "video_001.mkv").write_bytes(b"video-bytes")
    (logs_dir / "input_events.jsonl").write_text('{"event":"click"}\n', encoding="utf-8")

    monkeypatch.setattr(
        "api.utils.files.config.WINEBOT_RECORDING_INCLUDE_INPUT_TRACES", False
    )
    output_path = write_recording_artifact_manifest(str(session_dir), generated_by_action="stop")
    assert output_path is not None
    payload = json.loads(Path(output_path).read_text(encoding="utf-8"))
    artifact_paths = {item["path"] for item in payload["artifacts"]}
    assert "video_001.mkv" in artifact_paths
    assert "logs/input_events.jsonl" not in artifact_paths


def test_enforce_recording_retention_max_segments(tmp_path: Path, monkeypatch):
    session_dir = tmp_path / "session-retain"
    session_dir.mkdir(parents=True)
    for segment in (1, 2, 3):
        suffix = f"{segment:03d}"
        (session_dir / f"video_{suffix}.mkv").write_bytes(b"v")
        (session_dir / f"events_{suffix}.jsonl").write_text("{}", encoding="utf-8")
        (session_dir / f"segment_{suffix}.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr("api.utils.files.config.WINEBOT_RECORDING_RETENTION_MAX_SEGMENTS", 2)
    monkeypatch.setattr("api.utils.files.config.WINEBOT_RECORDING_RETENTION_MAX_AGE_DAYS", 0)
    monkeypatch.setattr("api.utils.files.config.WINEBOT_RECORDING_RETENTION_MAX_BYTES", 0)

    result = enforce_recording_retention(str(session_dir))
    assert "video_001.mkv" in result["deleted"]
    assert not (session_dir / "video_001.mkv").exists()
    assert (session_dir / "video_002.mkv").exists()
    assert (session_dir / "video_003.mkv").exists()
