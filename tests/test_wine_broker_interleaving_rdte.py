"""Pure deterministic adversarial schedule: split admission callbacks."""
import unittest

class Interleaving(unittest.TestCase):
    def test_split_reads_admit_stale_incarnation(self):
        broker={"session":"s","incarnation":7}
        first=broker["session"]
        broker.update(session="s",incarnation=8)
        second=broker["session"]
        self.assertEqual(first,second)
        self.assertNotEqual(7,broker["incarnation"])
        self.assertFalse(first==second and broker["incarnation"]==7)

    def test_atomic_snapshot_can_reject_old_owner(self):
        broker={"session":"s","incarnation":8}
        old=("s",7)
        current=(broker["session"],broker["incarnation"])
        self.assertNotEqual(old,current)

if __name__=="__main__":
    unittest.main()
