"""Bounded synthetic lease-epoch authority; not production InputBroker."""
import threading
import time
import secrets

class EpochBroker:
    def __init__(self, clock=None):
        self._lock = threading.RLock()
        self._clock = clock or time.monotonic
        self._epoch = 0
        self._lease = None
        self._collector = None

    def grant(self, session, owner, ttl):
        if not (type(session) is str and session and type(owner) is str and owner
                and type(ttl) in (int, float) and 0 < ttl <= 3600):
            return None
        with self._lock:
            self._epoch += 1
            self._lease = (session, owner, self._epoch, self._clock() + ttl)
            self._collector = None
            return self._epoch

    def _valid(self, session, owner, epoch):
        lease = self._lease
        return (lease is not None and lease[:3] == (session, owner, epoch)
                and self._clock() < lease[3])

    def admit(self, session, owner, epoch):
        with self._lock:
            if not self._valid(session, owner, epoch) or self._collector:
                return None
            generation = secrets.token_hex(16)
            self._collector = (session, owner, epoch, generation)
            return generation

    def validate(self, session, owner, epoch, generation):
        with self._lock:
            return (self._valid(session, owner, epoch)
                    and self._collector == (session, owner, epoch, generation))

    def revoke(self, session, owner, epoch):
        with self._lock:
            if not self._valid(session, owner, epoch):
                return False
            self._lease = None
            self._collector = None
            return True

    def renew(self, session, owner, epoch, ttl):
        if type(ttl) not in (int, float) or not 0 < ttl <= 3600:
            return False
        with self._lock:
            if not self._valid(session, owner, epoch):
                return False
            self._lease = (session, owner, epoch, self._clock() + ttl)
            return True
