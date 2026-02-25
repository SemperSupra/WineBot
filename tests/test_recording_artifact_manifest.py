import json
from pathlib import Path

from api.utils.files import (
    ensure_recording_timeline_id,
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
