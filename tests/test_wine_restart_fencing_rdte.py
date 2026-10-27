import unittest
from concurrent.futures import ThreadPoolExecutor
from rdte.wine11.restart_fencing_rdte import PersistentEpochStore, RestartFencedCollector, verify_replacement

class RestartFencingTests(unittest.TestCase):
    def test_shared_store_fences_restart(self):
        store = PersistentEpochStore()
        old = RestartFencedCollector(store)
        new = RestartFencedCollector(store)
        self.assertTrue(verify_replacement(old, new))
        self.assertFalse(new.validate(old.epoch))

    def test_fresh_store_is_not_durable(self):
        old = RestartFencedCollector(PersistentEpochStore())
        new = RestartFencedCollector(PersistentEpochStore())
        self.assertFalse(verify_replacement(old, new))

    def test_parallel_allocation_unique(self):
        store = PersistentEpochStore()
        with ThreadPoolExecutor(max_workers=16) as pool:
            epochs = list(pool.map(lambda _: store.allocate(), range(128)))
        self.assertEqual(len(set(epochs)), 128)
        self.assertEqual(max(epochs), 128)

    def test_revoked_owner_rejects_old_epoch(self):
        store = PersistentEpochStore()
        old = RestartFencedCollector(store)
        old.revoke()
        self.assertFalse(old.validate(old.epoch))

if __name__ == "__main__":
    unittest.main()
