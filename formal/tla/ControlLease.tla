---------------------------- MODULE ControlLease ----------------------------
EXTENDS Naturals, TLC

\* Bounded safety model: authority revocation and queued input are separate
\* steps. The broker must fence input at EFFECT time, not just queue time.
CONSTANT MaxEpoch
ASSUME MaxEpoch \in Nat \ {0}

VARIABLES epoch, granted, stopped, queued, lastEffect, effectWasAuthorized
vars == <<epoch, granted, stopped, queued, lastEffect, effectWasAuthorized>>

Init ==
  /\ epoch = 1
  /\ granted = FALSE
  /\ stopped = FALSE
  /\ queued = 0
  /\ lastEffect = 0
  /\ effectWasAuthorized = TRUE

Grant ==
  /\ ~granted /\ ~stopped /\ epoch < MaxEpoch
  /\ epoch' = epoch + 1
  /\ granted' = TRUE
  /\ UNCHANGED <<stopped, queued, lastEffect, effectWasAuthorized>>

QueueInput ==
  /\ granted /\ ~stopped /\ queued = 0
  /\ queued' = epoch
  /\ UNCHANGED <<epoch, granted, stopped, lastEffect, effectWasAuthorized>>

StopNow ==
  /\ granted /\ epoch < MaxEpoch
  /\ epoch' = epoch + 1
  /\ granted' = FALSE
  /\ stopped' = TRUE
  /\ UNCHANGED <<queued, lastEffect, effectWasAuthorized>>

AcknowledgeStop ==
  /\ stopped /\ queued = 0
  /\ stopped' = FALSE
  /\ UNCHANGED <<epoch, granted, queued, lastEffect, effectWasAuthorized>>

ExecuteInput ==
  /\ queued # 0 /\ granted /\ ~stopped /\ queued = epoch
  /\ lastEffect' = queued
  /\ effectWasAuthorized' = granted /\ ~stopped /\ queued = epoch
  /\ queued' = 0
  /\ UNCHANGED <<epoch, granted, stopped>>

DiscardStale ==
  /\ queued # 0 /\ (~granted \/ stopped \/ queued # epoch)
  /\ queued' = 0
  /\ UNCHANGED <<epoch, granted, stopped, lastEffect, effectWasAuthorized>>

Next == Grant \/ QueueInput \/ StopNow \/ AcknowledgeStop
        \/ ExecuteInput \/ DiscardStale

Spec == Init /\ [][Next]_vars

TypeOK ==
  /\ epoch \in 1..MaxEpoch
  /\ granted \in BOOLEAN
  /\ stopped \in BOOLEAN
  /\ queued \in 0..MaxEpoch
  /\ lastEffect \in 0..MaxEpoch
  /\ effectWasAuthorized \in BOOLEAN

NoUnauthorizedEffect == effectWasAuthorized
NoAgentWhileStopped == stopped => ~granted
=============================================================================
