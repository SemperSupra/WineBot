"""Actual EventBridge replay, schema, overflow and cursor checks."""
import json
import unittest
from rdte.wine11.event_bridge import EventBridge

def line(kind,seq):
    return json.dumps({"schema":"winebot.wine.event.v1","kind":kind,"sequence":seq})+"\\n"

class EventBridgeAdversarial(unittest.TestCase):
    def test_gap_fails_closed(self):
        b=EventBridge()
        self.assertTrue(b.ingest(line("ready",0)))
        self.assertFalse(b.ingest(line("show",2)))
        self.assertEqual(b.observe()["state"],"unqualified")
    def test_replay_fails_closed(self):
        b=EventBridge()
        self.assertTrue(b.ingest(line("ready",0)))
        self.assertTrue(b.ingest(line("show",1)))
        self.assertFalse(b.ingest(line("show",1)))
        self.assertEqual(b.observe()["events"],[])
    def test_overflow_terminal(self):
        b=EventBridge()
        self.assertTrue(b.ingest(line("ready",0)))
        self.assertFalse(b.ingest(line("overflow",1)))
        self.assertEqual(b.observe()["reason"],"source_overflow")
    def test_bounded_cursor_history_gap(self):
        b=EventBridge(capacity=2)
        self.assertTrue(b.ingest(line("ready",0)))
        for i in range(1,4):
            self.assertTrue(b.ingest(line("show",i)))
        self.assertEqual(b.observe(after=0)["state"],"history_gap")
if __name__=="__main__":
    unittest.main()
