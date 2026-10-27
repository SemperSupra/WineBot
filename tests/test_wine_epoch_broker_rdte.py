import unittest
from concurrent.futures import ThreadPoolExecutor
from rdte.wine11.epoch_broker_rdte import EpochBroker

class EpochBrokerTests(unittest.TestCase):
    def setUp(self):
        self.now = [100.]
        self.b = EpochBroker(lambda: self.now[0])
        self.epoch = self.b.grant("s", "owner", 10)

    def test_expiry_fails_closed(self):
        g = self.b.admit("s", "owner", self.epoch)
        self.now[0] = 110.
        self.assertFalse(self.b.validate("s", "owner", self.epoch, g))
        self.assertFalse(self.b.renew("s", "owner", self.epoch, 10))

    def test_regrant_fences_old_generation(self):
        g = self.b.admit("s", "owner", self.epoch)
        newer = self.b.grant("s", "owner", 10)
        self.assertGreater(newer, self.epoch)
        self.assertFalse(self.b.validate("s", "owner", self.epoch, g))
        self.assertIsNone(self.b.admit("s", "owner", self.epoch))
        self.assertIsNotNone(self.b.admit("s", "owner", newer))

    def test_revocation(self):
        g = self.b.admit("s", "owner", self.epoch)
        self.assertFalse(self.b.revoke("s", "attacker", self.epoch))
        self.assertTrue(self.b.revoke("s", "owner", self.epoch))
        self.assertFalse(self.b.validate("s", "owner", self.epoch, g))

    def test_renewal(self):
        g = self.b.admit("s", "owner", self.epoch)
        self.now[0] = 105.
        self.assertTrue(self.b.renew("s", "owner", self.epoch, 10))
        self.now[0] = 111.
        self.assertTrue(self.b.validate("s", "owner", self.epoch, g))

    def test_parallel_single_winner(self):
        with ThreadPoolExecutor(max_workers=16) as pool:
            r = list(pool.map(lambda _: self.b.admit("s", "owner", self.epoch), range(64)))
        self.assertEqual(sum(x is not None for x in r), 1)

    def test_invalid_inputs(self):
        self.assertIsNone(self.b.grant("s", "owner", 0))
        self.assertIsNone(self.b.grant("", "owner", 10))
        self.assertFalse(self.b.renew("s", "owner", self.epoch, -1))
        self.assertIsNone(self.b.admit("s", "wrong", self.epoch))

if __name__ == "__main__":
    unittest.main()
