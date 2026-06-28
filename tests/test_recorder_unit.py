import json
import unittest

from automation.recorder.models import Event, SessionManifest
from automation.recorder.subtitles import SubtitleGenerator


class TestRecorderModels(unittest.TestCase):
    def test_event_serialization(self):
        e = Event(
            session_id="sess-1",
            t_rel_ms=1000,
            t_epoch_ms=1600000000000,
            level="INFO",
            kind="test",
            message="Hello",
            pos={"x": 10, "y": 20, "w": 100, "h": 50},
        )
        json_str = e.to_json()
        data = json.loads(json_str)
        self.assertEqual(data["message"], "Hello")
        self.assertEqual(data["pos"]["x"], 10)
        self.assertEqual(data["schema_version"], "1.0")

        e2 = Event.from_json(json_str)
        self.assertEqual(e, e2)

    def test_event_from_json_backfills_schema_version(self):
        raw = {
            "session_id": "sess-1",
            "t_rel_ms": 1,
            "t_epoch_ms": 2,
            "level": "INFO",
            "kind": "test",
            "message": "legacy",
        }
        event = Event.from_json(json.dumps(raw))
        self.assertEqual(event.schema_version, "1.0")

    def test_manifest_from_json_backfills_schema_version(self):
        raw = {
            "session_id": "sess-1",
            "start_time_epoch": 1.0,
            "start_time_iso": "2026-01-01T00:00:00+00:00",
            "hostname": "host",
            "display": ":99",
            "resolution": "1280x720",
            "fps": 30,
            "git_sha": None,
        }
        manifest = SessionManifest.from_json(json.dumps(raw))
        self.assertEqual(manifest.schema_version, "1.0")


class TestSubtitles(unittest.TestCase):
    def test_vtt_generation(self):
        events = [
            Event("s1", 1000, 0, "I", "k", "First"),
            Event("s1", 5000, 0, "I", "k", "Second"),
        ]
        gen = SubtitleGenerator(events)
        vtt = gen.generate_vtt()

        self.assertIn("WEBVTT", vtt)
        self.assertIn(
            "00:00:01.000 --> 00:00:04.000", vtt
        )  # 1s to next event (min(1+3, 5)) -> 4s? No.
        # Logic: min(event.t_rel_ms + 3000, end_ms) -> min(1000+3000, 5000) = 4000
        self.assertIn("[K] First", vtt)
        self.assertIn("00:00:05.000 --> 00:00:08.000", vtt)  # Last event + 3s

    def test_ass_generation(self):
        events = [
            Event("s1", 1500, 0, "I", "annotation", "Note", pos={"x": 100, "y": 100})
        ]
        gen = SubtitleGenerator(events)
        ass = gen.generate_ass(1920, 1080)

        self.assertIn("[Script Info]", ass)
        self.assertIn("PlayResX: 1920", ass)
        # 1.5s -> 0:00:01.50
        self.assertIn(
            "Dialogue: 0,0:00:01.50,0:00:04.50,Default,,0,0,0,,[ANNOTATION] Note", ass
        )
        self.assertIn(
            "Dialogue: 1,0:00:01.50,0:00:04.50,Overlay,,0,0,0,,{\\pos(100,100)}Note",
            ass,
        )


if __name__ == "__main__":
    unittest.main()
