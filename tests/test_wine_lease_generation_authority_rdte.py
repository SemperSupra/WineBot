import unittest
from concurrent.futures import ThreadPoolExecutor
from rdte.wine11.lease_generation_authority_rdte import LeaseGenerationAuthority, SyntheticBrokerLeaseCell

class LeaseAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.a = LeaseGenerationAuthority()
        self.live = ["s", "lease1", "owner1"]
        self.current = lambda: tuple(self.live)

    def admit(self):
        return self.a.admit(*self.live, self.current)

    def test_valid_and_stale(self):
        gen = self.admit()
        self.assertIsNotNone(gen)
        self.assertTrue(self.a.validate(*self.live, gen, self.current))
        self.live[1] = "lease2"
        self.assertFalse(self.a.validate("s", "lease1", "owner1", gen, self.current))
        self.assertTrue(self.a.invalidate_if_changed(self.current))
        self.assertFalse(self.a.validate("s", "lease1", "owner1", gen, self.current))
        new = self.admit()
        self.assertNotEqual(gen, new)

    def test_duplicate_and_wrong_owner(self):
        gen = self.admit()
        self.assertIsNone(self.admit())
        self.assertFalse(self.a.retire("s", "lease1", "other", gen))
        self.assertTrue(self.a.retire("s", "lease1", "owner1", gen))
        self.assertFalse(self.a.retire("s", "lease1", "owner1", gen))

    def test_no_stale_owner_erase(self):
        old = self.admit()
        self.assertTrue(self.a.retire(*self.live, old))
        fresh = self.admit()
        self.assertFalse(self.a.retire(*self.live, old))
        self.assertTrue(self.a.validate(*self.live, fresh, self.current))

    def test_concurrent_single_winner(self):
        with ThreadPoolExecutor(max_workers=16) as pool:
            generations = list(pool.map(lambda _: self.admit(), range(64)))
        self.assertEqual(sum(x is not None for x in generations), 1)

    def test_broker_mismatch_and_bad_identity(self):
        self.assertIsNone(self.a.admit("s", "wrong", "owner1", self.current))
        self.assertIsNone(self.a.admit("", "lease1", "owner1", self.current))
        self.assertIsNone(self.a.admit("s", "lease1", True, self.current))
        self.assertIsNone(self.a.admit("s", "lease1", "owner1", lambda: None))

    def test_expired_lease_rejected(self):
        gen = self.admit()
        self.live[0] = "another"
        self.assertFalse(self.a.validate("s", "lease1", "owner1", gen, self.current))
        self.assertTrue(self.a.invalidate_if_changed(self.current))
        self.assertFalse(self.a.invalidate_if_changed(self.current))

class BrokerCellTests(unittest.TestCase):
    def test_transition_atomically_revokes_old_generation(self):
        cell = SyntheticBrokerLeaseCell()
        cell.transition("s", "lease1", "owner1")
        old = cell.admit("s", "lease1", "owner1")
        self.assertTrue(cell.validate("s", "lease1", "owner1", old))
        cell.transition("s", "lease2", "owner2")
        self.assertFalse(cell.validate("s", "lease1", "owner1", old))
        self.assertFalse(cell.retire("s", "lease1", "owner1", old))
        new = cell.admit("s", "lease2", "owner2")
        self.assertNotEqual(old, new)
        self.assertTrue(cell.validate("s", "lease2", "owner2", new))

    def test_parallel_admission_and_transition_no_stale_live_generation(self):
        cell = SyntheticBrokerLeaseCell()
        cell.transition("s", "lease1", "owner1")
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(
                lambda _: cell.admit("s", "lease1", "owner1"), range(24)))
        self.assertEqual(sum(x is not None for x in results), 1)
        old = next(x for x in results if x is not None)
        cell.transition("s", "lease2", "owner2")
        self.assertFalse(cell.validate("s", "lease1", "owner1", old))
        self.assertIsNone(cell.admit("s", "lease1", "owner1"))
        self.assertIsNotNone(cell.admit("s", "lease2", "owner2"))

    def test_wrong_broker_identity_denied(self):
        cell = SyntheticBrokerLeaseCell()
        cell.transition("s", "lease1", "owner1")
        self.assertIsNone(cell.admit("s", "lease1", "other"))
        self.assertIsNone(cell.admit("s", "wrong", "owner1"))
        self.assertIsNone(cell.admit("other", "lease1", "owner1"))

if __name__ == "__main__":
    unittest.main()
