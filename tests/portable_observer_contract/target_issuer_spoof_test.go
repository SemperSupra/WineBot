// SPDX-License-Identifier: MIT
// Synthetic-only registry incarnation collisions, NOT principal authentication.
package observercontract

import (
    "errors"
    "testing"
)

func TestTargetIssuerSeparatesSameNamespaceAcrossRegistryInstances(t *testing.T) {
    // Identical session, desktop, source, generation, target ref and epoch.
    // This is possible after a process restart unless the issuer is distinct.
    first,err:=NewTargetRegistry("session-a","desktop-a","source-a",9)
    if err!=nil {t.Fatal(err)}
    second,err:=NewTargetRegistry("session-a","desktop-a","source-a",9)
    if err!=nil {t.Fatal(err)}
    const sameRef="synthetic_opaque_target_token_0001"
    a,err:=first.BindTrustedRef(sameRef)
    if err!=nil {t.Fatal(err)}
    b,err:=second.BindTrustedRef(sameRef)
    if err!=nil {t.Fatal(err)}
    if a.Issuer=="" || b.Issuer=="" || a.Issuer==b.Issuer {
        t.Fatal("registry incarnation nonce missing or reused")
    }
    if a.Ref!=b.Ref || a.Epoch!=b.Epoch || a.Generation!=b.Generation {
        t.Fatal("test failed to manufacture equal namespace/epoch")
    }
    if first.Check(a)!=nil || second.Check(b)!=nil {t.Fatal("original stamp invalid")}
    if !errors.Is(second.Check(a),ErrTargetStale) || !errors.Is(first.Check(b),ErrTargetStale) {
        t.Fatal("different registry accepted same-namespace stamp")
    }
    swapped:=a
    swapped.Issuer=b.Issuer
    // This comparison-only model is deliberately not cryptographic.
    // A caller who can forge a complete stamp could match this comparison,
    // so it MUST NEVER be exposed as broker authorization.
    if !errors.Is(first.Check(swapped),ErrTargetStale) {
        t.Fatal("modified issuer passed original registry")
    }
}

func TestTargetIssuerRotatesAtomicallyWithGeneration(t *testing.T) {
    r,err:=NewTargetRegistry("s","d","p",3)
    if err!=nil {t.Fatal(err)}
    stamp,err:=r.BindTrustedRef("synthetic_opaque_target_token_0002")
    if err!=nil {t.Fatal(err)}
    if err:=r.Rotate(4);err!=nil {t.Fatal(err)}
    successor,err:=r.BindTrustedRef(stamp.Ref)
    if err!=nil {t.Fatal(err)}
    if successor.Issuer==stamp.Issuer || successor.Generation<=stamp.Generation ||
        successor.Epoch<=stamp.Epoch {t.Fatal("incarnation rotation reused identity or epoch")}
    if !errors.Is(r.Check(stamp),ErrTargetStale) {t.Fatal("stale stamp accepted after rotate")}
    if err:=r.Rotate(3);!errors.Is(err,ErrTargetStale) {t.Fatal("nonmonotonic generation accepted")}
    if err:=r.Check(successor);err!=nil {t.Fatal("rejected valid current stamp")}
}

func TestTargetIssuerDoesNotGrantActuation(t *testing.T) {
    r,err:=NewTargetRegistry("s","d","p",1)
    if err!=nil {t.Fatal(err)}
    stamp,err:=r.BindTrustedRef("synthetic_opaque_target_token_0003")
    if err!=nil {t.Fatal(err)}
    proposal:=Proposal{Principal:"actor",Desktop:stamp.Desktop,LeaseEpoch:1,
        TargetRef:stamp.Ref,TargetEpoch:stamp.Epoch,Operation:"window.activate"}
    authority:=Authority{Principal:"actor",Desktop:stamp.Desktop,LeaseEpoch:1,
        TargetRef:stamp.Ref,TargetEpoch:stamp.Epoch,Allowed:map[string]bool{}}
    if !errors.Is(ValidateProposal(proposal,authority),ErrUnauthorized) {
        t.Fatal("registry-issued synthetic stamp implied control")
    }
    // A passed synthetic predicate cannot independently establish postcondition.
    authority.Allowed["window.activate"]=true
    if err:=ValidateProposal(proposal,authority);err!=nil {t.Fatal(err)}
    if !errors.Is(VerifyPostcondition("","active",false),ErrOutcomeUnknown) {
        t.Fatal("preflight improperly accepted as verified action")
    }
}
