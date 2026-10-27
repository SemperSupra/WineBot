"""Synthetic restart fencing oracle: persistent epoch counter must survive owner reboot."""
import threading

class PersistentEpochStore:
    def __init__(self):
        self._lock = threading.RLock()
        self._epoch = 0

    def allocate(self):
        with self._lock:
            self._epoch += 1
            return self._epoch

class RestartFencedCollector:
    def __init__(self, store):
        self._store = store
        self._epoch = store.allocate()
        self._active = True

    @property
    def epoch(self):
        return self._epoch

    def validate(self, epoch):
        return self._active and epoch == self._epoch

    def revoke(self):
        self._active = False

def verify_replacement(old, new):
    """A new process must have an epoch above the old process."""
    return new.epoch > old.epoch
