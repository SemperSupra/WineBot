----------------------- MODULE PersistentSessionOwner -----------------------
EXTENDS TLC

\* Proposed persistent pointer protocol, NOT the current /tmp implementation.
\* A committed root owner remains discoverable across a fresh container's /tmp.
Owners == {"A", "B", "none"}
Phases == {"ready", "prepared", "committed", "down"}
VARIABLES phase, durable, volatile, reported, intent
vars == <<phase, durable, volatile, reported, intent>>

Init ==
  /\ phase = "ready"
  /\ durable = "A"
  /\ volatile = "A"
  /\ reported = "A"
  /\ intent = FALSE

Prepare ==
  /\ phase = "ready"
  /\ phase' = "prepared"
  /\ intent' = TRUE
  /\ UNCHANGED <<durable, volatile, reported>>

Commit ==
  /\ phase = "prepared"
  /\ phase' = "committed"
  /\ durable' = "B"
  /\ volatile' = "B"
  /\ reported' = "B"
  /\ intent' = FALSE

Crash ==
  /\ phase \in {"ready", "prepared", "committed"}
  /\ phase' = "down"
  /\ volatile' = "none"
  /\ reported' = "none"
  /\ UNCHANGED <<durable, intent>>

Recover ==
  /\ phase = "down"
  /\ phase' = "ready"
  /\ volatile' = durable
  /\ reported' = durable
  /\ intent' = FALSE
  /\ UNCHANGED durable

Next == Prepare \/ Commit \/ Crash \/ Recover
Spec == Init /\ [][Next]_vars

TypeOK ==
  /\ phase \in Phases
  /\ durable \in Owners
  /\ volatile \in Owners
  /\ reported \in Owners
  /\ intent \in BOOLEAN

NoFalseReady ==
  (phase \in {"ready", "committed"}) =>
    (volatile = durable /\ reported = durable /\ ~intent)
NoSplitVisibleOwner ==
  (volatile # "none" /\ reported # "none") =>
    (volatile = reported)
=============================================================================