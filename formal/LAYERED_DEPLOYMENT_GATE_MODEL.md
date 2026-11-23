# Two-lock deployment gate — bounded interleaving evidence, R040

The actual OCI gate is in WineBot draft PR #207. This independent source
workcell defines an abstract two-deployment protocol and exhaustively
enumerates all reachable states (to 14 transitions) under two locks:
`gate` for deployment initiation, `writer` for exclusive mutable state.

Properties checked:
- While a nonfailed deployment has prepared state but has not yet acquired
  its runtime writer lock, no other deployment can finish initialization.
- The state-init writer and the runtime writer cannot both own the same
  state lock; a controller dying during init invalidates the startup intent.
- The controller holds the deployment lock until the runtime writer has
  acquired its own exclusive lock, or an abort/fail-stop has happened.

**Deliberately unsafe model** releases the deployment gate after
`state-init`, before runtime admission. The checker must find an
interleaving: project A prepares; A releases gate early; project B
acquires gate, begins init and completes its own init while project A
still awaits runtime admission. The negative assertion is mandatory,
not an ignored expected failure.

Method: stdlib `unittest` BFS over immutable finite tuples, no network,
no external data or clock. This is **not TLC**, a mechanized proof of
the shell code, a fairness/liveness proof, a distributed fencing
guarantee, or a substitute for Docker Compose competing-project HIL
and independent release critic. Root, DAC_OVERRIDE, session control file
identity and full persistent CAS restart activation remain separate
security/admission gates. Run `python3 -m unittest
formal.tests.test_layered_deployment_gate_protocol -v`.

No changes to #207 source or to the protected branch. This intentionally
runs as a separate CI workcell while long Wine11 HIL runs.
