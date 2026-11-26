------------------------ MODULE ControlLeaseUnsafe -------------------------
\* Deliberately BROKEN negative control. TLC MUST find a counterexample:
\* queue under agent authority, STOP_NOW revokes, stale action executes anyway.
VARIABLES granted, queued, stopped, unauthorizedEffect
vars == <<granted, queued, stopped, unauthorizedEffect>>

Init ==
  /\ granted = FALSE
  /\ queued = FALSE
  /\ stopped = FALSE
  /\ unauthorizedEffect = FALSE

Grant ==
  /\ ~granted /\ ~stopped
  /\ granted' = TRUE
  /\ UNCHANGED <<queued, stopped, unauthorizedEffect>>

Queue ==
  /\ granted /\ ~queued
  /\ queued' = TRUE
  /\ UNCHANGED <<granted, stopped, unauthorizedEffect>>

Revoke ==
  /\ granted
  /\ granted' = FALSE
  /\ stopped' = TRUE
  /\ UNCHANGED <<queued, unauthorizedEffect>>

UnsafeExecute ==
  /\ queued
  /\ unauthorizedEffect' = ~granted \/ stopped
  /\ queued' = FALSE
  /\ UNCHANGED <<granted, stopped>>

Next == Grant \/ Queue \/ Revoke \/ UnsafeExecute
Spec == Init /\ [][Next]_vars

NoUnauthorizedEffect == ~unauthorizedEffect
=============================================================================
