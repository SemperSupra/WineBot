--------------------- MODULE SessionWriterFenceUnsafe ---------------------
EXTENDS Naturals, TLC

\* Deliberately BROKEN: two workers read the same epoch, then each writes.
\* Stale last-writer-wins commit must be rejected by mandatory TLC negative.
Writers == {"one", "two"}
Target(w) == IF w = "one" THEN "B" ELSE "C"
VARIABLES epoch, owner, phase, observed, staleCommit
vars == <<epoch, owner, phase, observed, staleCommit>>

Init ==
  /\ epoch = 1
  /\ owner = "A"
  /\ phase = [w \in Writers |-> "idle"]
  /\ observed = [w \in Writers |-> 0]
  /\ staleCommit = FALSE

Observe(w) ==
  /\ phase[w] = "idle"
  /\ phase' = [phase EXCEPT ![w] = "seen"]
  /\ observed' = [observed EXCEPT ![w] = epoch]
  /\ UNCHANGED <<epoch, owner, staleCommit>>

UnsafeCommit(w) ==
  /\ phase[w] = "seen"
  /\ owner' = Target(w)
  /\ epoch' = observed[w] + 1
  /\ staleCommit' = (staleCommit \/ (observed[w] # epoch))
  /\ phase' = [phase EXCEPT ![w] = "done"]
  /\ UNCHANGED observed

Next == \E w \in Writers : (Observe(w) \/ UnsafeCommit(w))
Spec == Init /\ [][Next]_vars

NoStaleWrite == ~staleCommit
=============================================================================