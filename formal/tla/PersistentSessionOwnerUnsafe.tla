-------------------- MODULE PersistentSessionOwnerUnsafe --------------------
EXTENDS TLC

\* Deliberately broken real-world pattern: only /tmp stores active pointer.
\* A new container invents another session while durable handover intent lives.
Owners == {"A", "C", "none"}
VARIABLES phase, durable, volatile, intent
vars == <<phase, durable, volatile, intent>>

Init ==
  /\ phase = "ready"
  /\ durable = "A"
  /\ volatile = "A"
  /\ intent = FALSE

Prepare ==
  /\ phase = "ready"
  /\ phase' = "prepared"
  /\ intent' = TRUE
  /\ UNCHANGED <<durable, volatile>>

Crash ==
  /\ phase = "prepared"
  /\ phase' = "down"
  /\ volatile' = "none"
  /\ UNCHANGED <<durable, intent>>

UnsafeFallback ==
  /\ phase = "down"
  /\ phase' = "ready"
  /\ volatile' = "C"
  /\ UNCHANGED <<durable, intent>>

Next == Prepare \/ Crash \/ UnsafeFallback
Spec == Init /\ [][Next]_vars
NoOrphanAtRest ==
  (phase = "ready") => (volatile = durable /\ ~intent)
=============================================================================