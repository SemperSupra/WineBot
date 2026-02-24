import os
import time

from api.core import recorder as recorder_core


def test_recorder_heartbeat_detects_stale_file(tmp_path, monkeypatch):
    session_dir = tmp_path / "session-hb-stale"
    session_dir.mkdir()
    video = session_dir / "video_001.mkv"
    video.write_bytes(b"1234")

    monkeypatch.setattr(
        recorder_core.config, "WINEBOT_RECORDER_HEARTBEAT_STALE_SECONDS", 1
    )
    monkeypatch.setattr(
        recorder_core.config, "WINEBOT_RECORDER_HEARTBEAT_GRACE_SECONDS", 0
    )
    recorder_core._heartbeat_cache.clear()

    assert recorder_core.recorder_heartbeat_check(str(session_dir)) is True
    time.sleep(1.2)
    assert recorder_core.recorder_heartbeat_check(str(session_dir)) is False


def test_recorder_heartbeat_accepts_growth(tmp_path, monkeypatch):
    session_dir = tmp_path / "session-hb-growth"
    session_dir.mkdir()
    video = session_dir / "video_001.mkv"
    video.write_bytes(b"1234")

    monkeypatch.setattr(
        recorder_core.config, "WINEBOT_RECORDER_HEARTBEAT_STALE_SECONDS", 5
    )
    monkeypatch.setattr(
        recorder_core.config, "WINEBOT_RECORDER_HEARTBEAT_GRACE_SECONDS", 0
    )
    recorder_core._heartbeat_cache.clear()

    assert recorder_core.recorder_heartbeat_check(str(session_dir)) is True
    with open(video, "ab") as handle:
        handle.write(b"5678")
    os.utime(video, None)
    assert recorder_core.recorder_heartbeat_check(str(session_dir)) is True
