"""Synthetic lease-bound collector generation authority; no runtime integration."""
import secrets
import threading

class LeaseGenerationAuthority:
    def __init__(self):
        self._lock = threading.RLock()
        self._active = None
        self._retired = set()

    def admit(self, session, lease, owner, current):
        """current() is the trusted broker snapshot (session, lease, owner)."""
        if not all(type(x) is str and 0 < len(x) <= 64 for x in (session, lease, owner)):
            return None
        with self._lock:
            if current() != (session, lease, owner):
                return None
            if self._active is not None:
                return None
            generation = secrets.token_hex(16)
            while generation in self._retired:
                generation = secrets.token_hex(16)
            self._active = (session, lease, owner, generation)
            return generation

    def validate(self, session, lease, owner, generation, current):
        with self._lock:
            return (
                self._active == (session, lease, owner, generation)
                and current() == (session, lease, owner)
            )

    def retire(self, session, lease, owner, generation):
        with self._lock:
            if self._active != (session, lease, owner, generation):
                return False
            self._retired.add(generation)
            self._active = None
            return True

    def invalidate_if_changed(self, current):
        with self._lock:
            if self._active is None:
                return False
            if current() == self._active[:3]:
                return False
            self._retired.add(self._active[3])
            self._active = None
            return True
