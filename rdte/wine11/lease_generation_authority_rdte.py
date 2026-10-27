"""Synthetic broker-serialized collector generation authority, not a runtime route."""
import secrets
import threading

class LeaseGenerationAuthority:
    def __init__(self):
        self._lock = threading.RLock()
        self._active = None
        self._retired = set()

    def admit(self, session, lease, owner, current):
        """current() must execute under the same broker-held lock as lease changes."""
        if not all(type(x) is str and 0 < len(x) <= 64 for x in (session, lease, owner)):
            return None
        with self._lock:
            if current() != (session, lease, owner) or self._active is not None:
                return None
            generation = secrets.token_hex(16)
            while generation in self._retired:
                generation = secrets.token_hex(16)
            self._active = (session, lease, owner, generation)
            return generation

    def validate(self, session, lease, owner, generation, current):
        with self._lock:
            return (self._active == (session, lease, owner, generation)
                    and current() == (session, lease, owner))

    def retire(self, session, lease, owner, generation):
        with self._lock:
            if self._active != (session, lease, owner, generation):
                return False
            self._retired.add(generation)
            self._active = None
            return True

    def invalidate_if_changed(self, current):
        with self._lock:
            if self._active is None or current() == self._active[:3]:
                return False
            self._retired.add(self._active[3])
            self._active = None
            return True

class SyntheticBrokerLeaseCell:
    """One lock owns broker identity AND generation mutations.

    A test double only. Production broker lease storage, persistence, process
    fencing and authenticated identity remain independent unqualified gates.
    """
    def __init__(self):
        self._lock = threading.RLock()
        self._identity = None
        self._authority = LeaseGenerationAuthority()

    def transition(self, session, lease, owner):
        with self._lock:
            self._identity = (session, lease, owner)
            self._authority.invalidate_if_changed(lambda: self._identity)

    def admit(self, session, lease, owner):
        with self._lock:
            return self._authority.admit(
                session, lease, owner, lambda: self._identity)

    def validate(self, session, lease, owner, generation):
        with self._lock:
            return self._authority.validate(
                session, lease, owner, generation, lambda: self._identity)

    def retire(self, session, lease, owner, generation):
        with self._lock:
            return self._authority.retire(session, lease, owner, generation)
