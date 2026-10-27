"""Adversarial, synthetic-only generation cursor tests; stdlib and no network."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import re
import unittest

from rdte.wine11.event_bridge import EventBridge
from rdte.wine11.generation_cursor_rdte import (
    CURSOR_SCHEMA, GenerationCursorView,
)


def line(kind, sequence):
    return json.dumps(
        {"schema": "winebot.wine.event.v1", "kind": kind, "sequence": sequence},
        separators=(",", ":"),
    )


def ready_bridge(capacity=128, kinds=("show", "location")):
    bridge = EventBridge(capacity=capacity)
    assert bridge.ingest(line("ready", 0))
    for i, kind in enumerate(kinds, start=1):
        assert bridge.ingest(line(kind, i))
    return bridge


class GenerationCursorTests(unittest.TestCase):
    SESSION = "synthetic-session"

    def setUp(self):
        self.bridge = ready_bridge()
        self.view = GenerationCursorView(self.SESSION, self.bridge)
        self.cursor = self.view.initial_cursor()

    def tearDown(self):
        self.view.close()

    def read(self, cursor=None, **kwargs):
        return self.view.read(
            self.SESSION, self.cursor if cursor is None else cursor, **kwargs,
        )

    def test_exact_versioned_cursor_and_valid_first_read(self):
        self.assertEqual(set(self.cursor), {
            "version", "session", "generation", "sequence",
        })
        self.assertEqual(self.cursor["version"], 1)
        self.assertEqual(self.cursor["session"], self.SESSION)
        self.assertRegex(self.cursor["generation"], r"^[0-9a-f]{32}$")
        self.assertEqual(self.cursor["sequence"], 0)
        snap = self.read()
        self.assertEqual(snap["schema"], CURSOR_SCHEMA)
        self.assertEqual(snap["state"], "ready")
        self.assertEqual(snap["events"], [
            {"kind": "show", "sequence": 1},
            {"kind": "location", "sequence": 2},
        ])
        self.assertEqual(snap["next_cursor"]["sequence"], 2)
        self.assertEqual(
            snap["next_cursor"]["generation"], self.cursor["generation"],
        )

    def test_pagination_and_independent_readers(self):
        first = self.read(limit=1)
        self.assertEqual(first["events"], [{"kind": "show", "sequence": 1}])
        second = self.read(first["next_cursor"], limit=1)
        self.assertEqual(second["events"], [{"kind": "location", "sequence": 2}])
        self.assertEqual(self.read(limit=1)["events"], first["events"])
        self.assertEqual(self.read(second["next_cursor"])["events"], [])

    def test_three_audiences_share_consistent_non_destructive_snapshot(self):
        def read_for(_audience):
            return self.read()
        with ThreadPoolExecutor(max_workers=3) as pool:
            states = list(pool.map(
                read_for, ("human", "automation", "agent"),
            ))
        self.assertEqual(states, [states[0]] * 3)
        states[0]["events"][0]["kind"] = "tampered"
        self.assertEqual(self.read()["events"][0]["kind"], "show")

    def test_restarted_collector_cannot_reinterpret_old_sequence_one(self):
        first = self.read(limit=1)["next_cursor"]
        old_generation = self.cursor["generation"]
        self.view.close()
        replacement = GenerationCursorView(
            self.SESSION, ready_bridge(kinds=("focus",)),
        )
        try:
            self.assertNotEqual(
                replacement.initial_cursor()["generation"], old_generation,
            )
            result = replacement.read(self.SESSION, first)
            self.assertEqual(result["state"], "stale_generation")
            self.assertEqual(result["events"], [])
            self.assertIsNone(result["next_cursor"])
            fresh = replacement.read(
                self.SESSION, replacement.initial_cursor(),
            )
            self.assertEqual(fresh["events"], [
                {"sequence": 1, "kind": "focus"},
            ])
        finally:
            replacement.close()

    def test_session_misbinding_has_no_data_or_new_cursor(self):
        self.assertEqual(self.view.read("wrong-session", self.cursor)["state"],
                         "unavailable")
        forged = copy.deepcopy(self.cursor)
        forged["session"] = "different-session"
        out = self.read(forged)
        self.assertEqual(out["state"], "session_mismatch")
        self.assertEqual(out["events"], [])
        self.assertIsNone(out["next_cursor"])

    def test_unknown_generation_is_not_a_valid_continuation(self):
        forged = copy.deepcopy(self.cursor)
        forged["generation"] = "0" * 32
        if forged["generation"] == self.cursor["generation"]:
            forged["generation"] = "f" * 32
        out = self.read(forged)
        self.assertEqual(out["state"], "stale_generation")
        self.assertEqual(out["events"], [])
        self.assertIsNone(out["next_cursor"])

    def test_malformed_cursor_is_fail_closed(self):
        broken = [
            None, [], 1, "synthetic", {}, self.cursor | {"unexpected": 1},
            {k: v for k, v in self.cursor.items() if k != "sequence"},
        ]
        for field, invalids in {
            "version": [0, 2, True, "1", 1.0],
            "session": ["", "bad/path", 4, "x" * 65, None],
            "generation": ["", "f" * 31, "G" * 32, 4, None],
            "sequence": [-1, True, 1.0, "1", None],
        }.items():
            for item in invalids:
                attempt = copy.deepcopy(self.cursor)
                attempt[field] = item
                broken.append(attempt)
        for candidate in broken:
            with self.subTest(candidate_type=type(candidate).__name__):
                result = self.view.read(self.SESSION, candidate)
                self.assertEqual(result["state"], "invalid_cursor")
                self.assertEqual(result["events"], [])
                self.assertIsNone(result["next_cursor"])

    def test_limit_must_be_bounded_strict_integer(self):
        for limit in (0, 129, True, 1.0, -1, "2", None):
            with self.subTest(limit=limit):
                self.assertEqual(
                    self.read(limit=limit)["state"], "invalid_cursor",
                )

    def test_future_sequence_cannot_advance_without_source(self):
        ahead = copy.deepcopy(self.cursor)
        ahead["sequence"] = 999999
        self.assertEqual(self.read(ahead)["state"], "invalid_cursor")
        self.assertIsNone(self.read(ahead)["next_cursor"])

    def test_retention_gap_is_not_silent_resynchronization(self):
        bridge = ready_bridge(capacity=2, kinds=(
            "show", "location", "focus",
        ))
        view = GenerationCursorView(self.SESSION, bridge)
        try:
            gap = view.read(self.SESSION, view.initial_cursor())
            self.assertEqual(gap["state"], "history_gap")
            self.assertEqual(gap["events"], [])
            self.assertIsNone(gap["next_cursor"])
        finally:
            view.close()

    def test_not_ready_does_not_fabricate_cursor_progress(self):
        view = GenerationCursorView(self.SESSION, EventBridge())
        try:
            result = view.read(self.SESSION, view.initial_cursor())
            self.assertEqual(result["state"], "not_ready")
            self.assertIsNone(result["next_cursor"])
        finally:
            view.close()

    def test_source_gap_failure_erases_and_preserves_reason(self):
        self.assertFalse(self.bridge.ingest(line("location", 4)))
        state = self.read()
        self.assertEqual((state["state"], state["reason"]),
                         ("unqualified", "source_gap"))
        self.assertEqual(state["events"], [])
        self.assertIsNone(state["next_cursor"])

    def test_terminal_overflow_is_unqualified(self):
        self.assertFalse(self.bridge.ingest(line("overflow", 3)))
        state = self.read()
        self.assertEqual((state["state"], state["reason"]),
                         ("unqualified", "source_overflow"))
        self.assertEqual(state["events"], [])

    def test_close_erases_and_refuses_reuse(self):
        self.view.close()
        self.assertEqual(self.read()["state"], "unavailable")
        self.assertIsNone(self.view.initial_cursor())
        self.assertEqual(self.bridge.observe()["events"], [])
        self.view.close()

    def test_stale_close_cannot_erase_separate_replacement_bridge(self):
        replacement = GenerationCursorView(
            "new-session", ready_bridge(kinds=("focus",)),
        )
        try:
            self.view.close()
            self.assertEqual(
                replacement.read(
                    "new-session", replacement.initial_cursor(),
                )["events"], [{"kind": "focus", "sequence": 1}],
            )
        finally:
            replacement.close()

    def test_bad_session_or_bridge_constructor_rejected(self):
        for value in ("", "bad/path", "x" * 65, None, 1, True):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(ValueError):
                    GenerationCursorView(value, EventBridge())
        with self.assertRaises(TypeError):
            GenerationCursorView("synthetic", object())

    def test_no_raw_identifiers_or_unexpected_fields_in_outputs(self):
        result = self.read()
        self.assertEqual(set(result), {
            "schema", "state", "events", "next_cursor",
        })
        self.assertEqual(set(result["next_cursor"]), {
            "version", "session", "generation", "sequence",
        })
        self.assertNotIn("hwnd", json.dumps(result).lower())
        self.assertNotIn("pid", json.dumps(result).lower())
        self.assertNotIn("token", json.dumps(result).lower())
        self.assertTrue(re.fullmatch(
            r"[0-9a-f]{32}", result["next_cursor"]["generation"],
        ))


if __name__ == "__main__":
    unittest.main()
