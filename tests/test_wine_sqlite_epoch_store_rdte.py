import multiprocessing
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from rdte.wine11.sqlite_epoch_store_rdte import DurableEpochStore

def allocate_in_process(path, queue):
    queue.put(DurableEpochStore(path).allocate())

class DurableEpochTests(unittest.TestCase):
    def test_reopen_advances(self):
        with tempfile.TemporaryDirectory() as d:
            p = str(Path(d) / "epoch.db")
            self.assertEqual(DurableEpochStore(p).allocate(), 1)
            self.assertEqual(DurableEpochStore(p).allocate(), 2)

    def test_parallel_threads_unique(self):
        with tempfile.TemporaryDirectory() as d:
            p = str(Path(d) / "epoch.db")
            store = DurableEpochStore(p)
            with ThreadPoolExecutor(max_workers=8) as pool:
                epochs = list(pool.map(lambda _: store.allocate(), range(24)))
            self.assertEqual(sorted(epochs), list(range(1,25)))

    def test_separate_processes(self):
        with tempfile.TemporaryDirectory() as d:
            p = str(Path(d) / "epoch.db")
            q = multiprocessing.Queue()
            jobs = [multiprocessing.Process(target=allocate_in_process,args=(p,q)) for _ in range(8)]
            for j in jobs: j.start()
            for j in jobs: j.join(10)
            self.assertTrue(all(j.exitcode == 0 for j in jobs))
            self.assertEqual(sorted(q.get(timeout=2) for _ in jobs), list(range(1,9)))

    def test_rollback_does_not_consume_epoch(self):
        with tempfile.TemporaryDirectory() as d:
            p = str(Path(d) / "epoch.db")
            store = DurableEpochStore(p)
            import sqlite3
            with sqlite3.connect(p) as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("UPDATE epoch SET value=value+1 WHERE id=1")
                db.rollback()
            self.assertEqual(store.allocate(), 1)

if __name__ == "__main__":
    unittest.main()
