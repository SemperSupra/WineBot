------------------------- MODULE ReleaseAdmission --------------------------
EXTENDS Naturals

\* Abstract artifact generation IDs, not actual content digests.
\* Every evidence link must bind to the SAME exact source generation.
VARIABLES source, qualified, projected, built, pinned, approved, phase
vars == <<source, qualified, projected, built, pinned, approved, phase>>
Stages == {"candidate", "qualified", "projected", "built", "pinned", "accepted"}

Init ==
  /\ source = 1
  /\ qualified = 0
  /\ projected = 0
  /\ built = 0
  /\ pinned = 0
  /\ approved = FALSE
  /\ phase = "candidate"

Qualify ==
  /\ phase = "candidate"
  /\ qualified' = source
  /\ phase' = "qualified"
  /\ UNCHANGED <<source, projected, built, pinned, approved>>

ApproveAndProject ==
  /\ phase = "qualified" /\ qualified = source
  /\ projected' = source
  /\ approved' = TRUE
  /\ phase' = "projected"
  /\ UNCHANGED <<source, qualified, built, pinned>>

Build ==
  /\ phase = "projected" /\ approved /\ projected = source
  /\ built' = source
  /\ phase' = "built"
  /\ UNCHANGED <<source, qualified, projected, pinned, approved>>

Pin ==
  /\ phase = "built" /\ built = source
  /\ pinned' = source
  /\ phase' = "pinned"
  /\ UNCHANGED <<source, qualified, projected, built, approved>>

Accept ==
  /\ phase = "pinned"
  /\ qualified = source /\ projected = source
  /\ built = source /\ pinned = source /\ approved
  /\ phase' = "accepted"
  /\ UNCHANGED <<source, qualified, projected, built, pinned, approved>>

SourceChanges ==
  /\ phase # "accepted" /\ source = 1
  /\ source' = 2
  /\ approved' = FALSE
  /\ phase' = "candidate"
  /\ UNCHANGED <<qualified, projected, built, pinned>>

Next == Qualify \/ ApproveAndProject \/ Build \/ Pin \/ Accept \/ SourceChanges
Spec == Init /\ [][Next]_vars

TypeOK ==
  /\ source \in {1,2}
  /\ qualified \in 0..2 /\ projected \in 0..2
  /\ built \in 0..2 /\ pinned \in 0..2
  /\ approved \in BOOLEAN /\ phase \in Stages

NoStaleAcceptedArtifact ==
  (phase = "accepted") =>
    (approved /\ qualified = source /\ projected = source /\
     built = source /\ pinned = source)
=============================================================================
