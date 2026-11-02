// SPDX-License-Identifier: MIT
// Synthetic, read-only integration qualification of independently pinned
// portable observer, scoped fanout, target incarnation and deny-by-default
// actuator preflight. No Win32 resolver, session broker, action executor or RPC.
package observercontract

import (
  "encoding/json"
  "errors"
  "strings"
  "testing"
)

const syntheticRef = "synthetic_opaque_target_token_0001"

func TestIntegratedReadOnlyInspectAndNoImplicitAuthority(t *testing.T) {
  // A trusted issuer is emulated, NOT implemented. All refs are synthetic.
  registry,err:=NewTargetRegistry("session-A","desktop-A","source-A",1)
  if err!=nil {t.Fatal(err)}
  stamp,err:=registry.BindTrustedRef(syntheticRef)
  if err!=nil {t.Fatal(err)}
  relay,err:=NewScopedRelay("synthetic-stream-1",Source,1,4)
  if err!=nil {t.Fatal(err)}
  if err:=relay.Accept(Frame{Contract:Contract,Stream:"synthetic-stream-1",Source:Source,Sequence:0,Status:"ready"});err!=nil {t.Fatal(err)}
  inspect,err:=relay.NewBridge("wininspect")
  if err!=nil {t.Fatal(err)}
  agent,err:=relay.NewBridge("agent")
  if err!=nil {t.Fatal(err)}
  defer inspect.Close();defer agent.Close()
  if err:=relay.Accept(Frame{Contract:Contract,Stream:"synthetic-stream-1",Source:Source,Sequence:1,Status:"observed",Kind:"window.shown"});err!=nil {t.Fatal(err)}
  for _,b:=range []*ScopedBridge{inspect,agent} {
    hints,err:=b.Poll(4)
    if err!=nil || len(hints)!=1 || hints[0].Scope!="desktop" || hints[0].Reason!="window.shown" {
      t.Fatalf("bad broad reinspection hints: %+v, %v",hints,err)
    }
    data,err:=json.Marshal(hints)
    if err!=nil {t.Fatal(err)}
    for _,field:=range []string{"target_ref","target_epoch","hwnd","pid","lease","action","principal"} {
      if strings.Contains(strings.ToLower(string(data)),field) {t.Fatalf("leaked or implied authority: %s",field)}
    }
  }
  proposal:=Proposal{Principal:"actor-A",Desktop:stamp.Desktop,LeaseEpoch:1,
    TargetRef:stamp.Ref,TargetEpoch:stamp.Epoch,Operation:"window.activate"}
  // Matching data is insufficient: no authorized operation has been admitted.
  noControl:=Authority{Principal:"actor-A",Desktop:stamp.Desktop,LeaseEpoch:1,
    TargetRef:stamp.Ref,TargetEpoch:stamp.Epoch,Allowed:map[string]bool{}}
  if !errors.Is(ValidateProposal(proposal,noControl),ErrUnauthorized) {
    t.Fatal("observation incorrectly granted actuation")
  }
  // The predicate itself is not a live broker or a performed action.
  allowOnlyForSyntheticComparison:=noControl
  allowOnlyForSyntheticComparison.Allowed=map[string]bool{"window.activate":true}
  if err:=ValidateProposal(proposal,allowOnlyForSyntheticComparison);err!=nil {t.Fatal(err)}
  if !errors.Is(VerifyPostcondition("","active",false),ErrOutcomeUnknown) {
    t.Fatal("preflight success promoted to successful action")
  }
  if err:=registry.Revoke(stamp);err!=nil {t.Fatal(err)}
  if !errors.Is(registry.Check(stamp),ErrTargetStale) {
    t.Fatal("revoked synthetic stamp survived")
  }
  // A previous matching authority must NOT be treated as a fresh registry check.
  if err:=registry.Rotate(2);err!=nil {t.Fatal(err)}
  if !errors.Is(registry.Check(stamp),ErrTargetStale) {
    t.Fatal("producer incarnation rollover failed to fence stamp")
  }
}

func TestIntegratedGapInvalidatesAllHintsAndRejectsStaleLease(t *testing.T) {
  relay,err:=NewScopedRelay("stream-A",Source,7,2)
  if err!=nil {t.Fatal(err)}
  _=relay.Accept(Frame{Contract:Contract,Stream:"stream-A",Source:Source,Sequence:0,Status:"ready"})
  consumer,err:=relay.NewBridge("automation")
  if err!=nil {t.Fatal(err)}
  defer consumer.Close()
  _=relay.Accept(Frame{Contract:Contract,Stream:"stream-A",Source:Source,Sequence:1,Status:"observed",Kind:"window.shown"})
  _=relay.Accept(Frame{Contract:Contract,Stream:"stream-A",Source:Source,Sequence:2,Status:"observed",Kind:"window.location_changed"})
  _=relay.Accept(Frame{Contract:Contract,Stream:"stream-A",Source:Source,Sequence:3,Status:"observed",Kind:"window.hidden"})
  if _,err:=consumer.Poll(4);!errors.Is(err,ErrReinspectionRequired) {
    t.Fatalf("lost cursor accepted: %v",err)
  }
  if err:=relay.Accept(Frame{Contract:Contract,Stream:"stream-OLD",Source:Source,Sequence:4,Status:"observed",Kind:"window.created"});!errors.Is(err,ErrRelayStale) {
    t.Fatalf("mixed stream accepted: %v",err)
  }
  if _,err:=consumer.Poll(4);!errors.Is(err,ErrReinspectionRequired) {
    t.Fatal("poisoned relay returned observations")
  }
  p:=Proposal{Principal:"actor-A",Desktop:"desktop-A",LeaseEpoch:5,
    TargetRef:syntheticRef,TargetEpoch:2,Operation:"window.activate"}
  a:=Authority{Principal:"actor-A",Desktop:"desktop-A",LeaseEpoch:6,
    TargetRef:syntheticRef,TargetEpoch:2,Allowed:map[string]bool{"window.activate":true}}
  if !errors.Is(ValidateProposal(p,a),ErrLeaseConflict) {
    t.Fatal("stale lease promoted on observation loss")
  }
}
