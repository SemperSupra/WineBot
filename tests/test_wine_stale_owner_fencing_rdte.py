"""Synthetic stale-owner resource-side fencing oracle, not production broker."""
import unittest

class Resource:
    def __init__(self):
        self.epoch = 0
        self.incarnation = None
        self.running = False
        self.mutations = []

    def admit(self, incarnation, epoch):
        if epoch <= self.epoch:
            return False
        self.incarnation = incarnation
        self.epoch = epoch
        self.running = True
        self.mutations.append(("admit", incarnation, epoch))
        return True

    def shutdown(self, incarnation, epoch):
        if incarnation != self.incarnation or epoch != self.epoch:
            return False
        self.running = False
        self.mutations.append(("shutdown", incarnation, epoch))
        return True

class FencingTests(unittest.TestCase):
    def test_delayed_shutdown_cannot_kill_successor(self):
        r=Resource()
        self.assertTrue(r.admit("owner-a",41))
        self.assertTrue(r.admit("owner-b",42))
        before=list(r.mutations)
        self.assertFalse(r.shutdown("owner-a",41))
        self.assertEqual(r.mutations,before)
        self.assertTrue(r.running)
        self.assertTrue(r.shutdown("owner-b",42))

    def test_delayed_revoke_cannot_reuse_generation(self):
        r=Resource()
        self.assertTrue(r.admit("owner-a",41))
        self.assertTrue(r.admit("owner-b",42))
        self.assertFalse(r.admit("owner-c",41))
        self.assertFalse(r.admit("owner-c",42))
        self.assertEqual(r.incarnation,"owner-b")

    def test_identity_mismatch_rejected_even_at_same_epoch(self):
        r=Resource()
        self.assertTrue(r.admit("owner-a",41))
        before=list(r.mutations)
        self.assertFalse(r.shutdown("imposter",41))
        self.assertEqual(r.mutations,before)

if __name__=="__main__":
    unittest.main()
