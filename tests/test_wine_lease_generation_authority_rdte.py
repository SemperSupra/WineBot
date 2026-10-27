import unittest
from concurrent.futures import ThreadPoolExecutor
from rdte.wine11.lease_generation_authority_rdte import LeaseGenerationAuthority

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

if __name__ == "__main__":
    unittest.main()
