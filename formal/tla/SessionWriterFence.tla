------------------------ MODULE SessionWriterFence ------------------------
EXTENDS Naturals, TLC

\* Two independently scheduled workers use one durable logical owner.
\* This model describes a proposed fencing protocol, NOT existing WineBot.
CONSTANT MaxEpoch
ASSUME MaxEpoch \in Nat \ {0}
Writers == {"one", "two"}
Sessions == {"A", "B", "C"}
Phases == {"idle", "seen", "done"}
Target(w) == IF w = "one" THEN "B" ELSE "C"

VARIABLES epoch, owner, holder, phase, observed, staleCommit
vars == <<epoch, owner, holder, phase, observed, staleCommit>>

Init ==
  /\ epoch = 1
  /\ owner = "A"
  /\ holder = "none"
  /\ phase = [w \in Writers |-> "idle"]
  /\ observed = [w \in Writers |-> 0]
  /\ staleCommit = FALSE

Acquire(w) ==
  /\ holder = "none"
  /\ phase[w] = "idle"
  /\ epoch < MaxEpoch
  /\ holder' = w
  /\ phase' = [phase EXCEPT ![w] = "seen"]
  /\ observed' = [observed EXCEPT ![w] = epoch]
  /\ UNCHANGED <<epoch, owner, staleCommit>>

Commit(w) ==
  /\ holder = w
  /\ phase[w] = "seen"
  /\ observed[w] = epoch
  /\ epoch < MaxEpoch
  /\ owner' = Target(w)
  /\ epoch' = epoch + 1
  /\ holder' = "none"
  /\ phase' = [phase EXCEPT ![w] = "done"]
  /\ UNCHANGED <<observed, staleCommit>>

Crash(w) ==
  /\ holder = w
  /\ phase[w] = "seen"
  /\ holder' = "none"
  /\ phase' = [phase EXCEPT ![w] = "done"]
  /\ UNCHANGED <<epoch, owner, observed, staleCommit>>

Next == \E w \in Writers : (Acquire(w) \/ Commit(w) \/ Crash(w))
Spec == Init /\ [][Next]_vars

TypeOK ==
  /\ epoch \in 1..MaxEpoch
  /\ owner \in Sessions
  /\ holder \in Writers \cup {"none"}
  /\ phase \in [Writers -> Phases]
  /\ observed \in [Writers -> 0..MaxEpoch]
  /\ staleCommit \in BOOLEAN

NoStaleWrite == ~staleCommit
NoConcurrentPrepared ==
  \A w \in Writers : (phase[w] = "seen" => holder = w)
NoFalseInitialOwner == epoch = 1 => owner = "A"
=============================================================================