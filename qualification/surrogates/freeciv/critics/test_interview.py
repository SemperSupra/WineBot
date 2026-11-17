"""Offline model-interview scoring / negative checks (zero model downloads)."""
import importlib.util
import json
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("reversing_model_interview", Path(__file__).with_name("interview.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Tests(unittest.TestCase):
    def test_allowlist(self):
        self.assertEqual(set(m.MODEL), {"reasoning", "vision", "audio"})
        with self.assertRaises(ValueError):
            m.admit("arbitrary-api")

    def test_reasoning_strict_evidence(self):
        value = json.dumps({"verdict":"REJECT","evidence_refs":["fixture:clock"],
                            "next_action":"collect_more_evidence"})
        self.assertTrue(m.evaluate_reasoning_reply(value, "REJECT",["fixture:clock"]))
        self.assertFalse(m.evaluate_reasoning_reply(value, "ACCEPT",["fixture:clock"]))
        self.assertFalse(m.evaluate_reasoning_reply(value, "REJECT",["fixture:fake"]))

    def test_model_fabricated_authorization_rejected(self):
        value = json.dumps({"verdict":"REJECT","evidence_refs":["fixture:clock"],
                            "next_action":"collect_more_evidence", "authorize":"write"})
        self.assertFalse(m.evaluate_reasoning_reply(value, "REJECT",["fixture:clock"]))

    def test_non_json_fail_closed(self):
        self.assertFalse(m.evaluate_reasoning_reply("Sure, looks fine", "REJECT",["fixture:clock"]))

    def test_visual_ambiguous_fail_closed(self):
        self.assertEqual(m.classify_motion("left and right"), "unknown")
        self.assertEqual(m.classify_motion("right"), "right")
        self.assertEqual(m.classify_motion("I cannot tell"), "unknown")

    def test_summary_requires_bools(self):
        with self.assertRaises(ValueError):
            m.summarize("x","y","z",{"ok":1},1,"sha")

    def test_partial_does_not_pass(self):
        x=m.summarize("vision","m","r",{"positive":True,"negative":False},1,"hash")
        self.assertEqual(x["status"],"UNQUALIFIED")


if __name__=="__main__":
    unittest.main()
