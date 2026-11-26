-------------------------- MODULE SessionHandover ---------------------------
EXTENDS TLC

\* Logical committed owner is distinct from tentative pointer/profile/broker.
\* Crash recovery must converge all projections back to the committed owner.
Sessions == {"A", "B"}
Phases == {"idle", "prepared", "pointer_written", "profile_linked",
           "broker_switched", "committed", "recovering"}

VARIABLES phase, committed, pointer, profile, broker, intent
vars == <<phase, committed, pointer, profile, broker, intent>>

Init ==
  /\ phase = "idle"
  /\ committed = "A"
  /\ pointer = "A"
  /\ profile = "A"
  /\ broker = "A"
  /\ intent = FALSE

Prepare ==
  /\ phase = "idle" /\ committed = "A"
  /\ phase' = "prepared"
  /\ intent' = TRUE
  /\ UNCHANGED <<committed, pointer, profile, broker>>

WritePointer ==
  /\ phase = "prepared"
  /\ phase' = "pointer_written"
  /\ pointer' = "B"
  /\ UNCHANGED <<committed, profile, broker, intent>>

LinkProfile ==
  /\ phase = "pointer_written"
  /\ phase' = "profile_linked"
  /\ profile' = "B"
  /\ UNCHANGED <<committed, pointer, broker, intent>>

SwitchBroker ==
  /\ phase = "profile_linked"
  /\ phase' = "broker_switched"
  /\ broker' = "B"
  /\ UNCHANGED <<committed, pointer, profile, intent>>

Commit ==
  /\ phase = "broker_switched"
  /\ pointer = "B" /\ profile = "B" /\ broker = "B"
  /\ committed' = "B"
  /\ phase' = "committed"
  /\ intent' = FALSE
  /\ UNCHANGED <<pointer, profile, broker>>

Crash ==
  /\ phase \in {"prepared", "pointer_written", "profile_linked",
               "broker_switched"}
  /\ phase' = "recovering"
  /\ UNCHANGED <<committed, pointer, profile, broker, intent>>

Recover ==
  /\ phase = "recovering"
  /\ pointer' = committed
  /\ profile' = committed
  /\ broker' = committed
  /\ phase' = "idle"
  /\ intent' = FALSE
  /\ UNCHANGED committed

Next == Prepare \/ WritePointer \/ LinkProfile \/ SwitchBroker
        \/ Commit \/ Crash \/ Recover

Spec == Init /\ [][Next]_vars

TypeOK ==
  /\ phase \in Phases
  /\ committed \in Sessions
  /\ pointer \in Sessions
  /\ profile \in Sessions
  /\ broker \in Sessions
  /\ intent \in BOOLEAN

ConvergedAtRest ==
  (phase \in {"idle", "committed"}) =>
    (pointer = committed /\ profile = committed /\
     broker = committed /\ ~intent)
NoFalseCommit ==
  (phase = "committed") =>
    (committed = "B" /\ pointer = "B" /\
     profile = "B" /\ broker = "B")
=============================================================================
