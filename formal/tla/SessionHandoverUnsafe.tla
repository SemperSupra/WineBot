---------------------- MODULE SessionHandoverUnsafe ----------------------
\* Deliberately BROKEN crash-recovery model. After pointer replacement the
\* process dies, then an unprepared startup declares IDLE without reconciling
\* the profile and broker. TLC must expose a split-owner resting state.
VARIABLES phase, committed, pointer, profile, broker
vars == <<phase, committed, pointer, profile, broker>>

Init ==
  /\ phase = "idle"
  /\ committed = "A"
  /\ pointer = "A"
  /\ profile = "A"
  /\ broker = "A"

Prepare ==
  /\ phase = "idle"
  /\ phase' = "prepared"
  /\ UNCHANGED <<committed, pointer, profile, broker>>

WritePointer ==
  /\ phase = "prepared"
  /\ pointer' = "B"
  /\ phase' = "pointer_written"
  /\ UNCHANGED <<committed, profile, broker>>

CrashWithoutRecovery ==
  /\ phase = "pointer_written"
  /\ phase' = "idle"
  /\ UNCHANGED <<committed, pointer, profile, broker>>

Next == Prepare \/ WritePointer \/ CrashWithoutRecovery
Spec == Init /\ [][Next]_vars

ConvergedAtRest ==
  (phase = "idle") =>
    (pointer = committed /\ profile = committed /\ broker = committed)
=============================================================================
