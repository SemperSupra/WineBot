// SPDX-License-Identifier: MIT
package observercontract

import (
    "errors"
    "testing"
)

const refA = "SyntheticOpaqueTargetToken_AAAA01"
const refB = "SyntheticOpaqueTargetToken_BBBB02"

func TestTargetRegistryGenerationAndABA(t *testing.T) {
    r, err := NewTargetRegistry("session-A", "desktop-A", "source-A", 7)
    if err != nil { t.Fatal(err) }
    a, err := r.BindTrustedRef(refA)
    if err != nil || r.Check(a) != nil { t.Fatalf("bind/check: %v",err) }
    if _,err=r.BindTrustedRef(refA); !errors.Is(err,ErrTargetDuplicate) {t.Fatalf("duplicate: %v",err)}
    if err=r.Revoke(a);err!=nil {t.Fatal(err)}
    if !errors.Is(r.Check(a),ErrTargetStale) {t.Fatal("revoked stamp accepted")}
    replacement,err:=r.BindTrustedRef(refA)
    if err!=nil || replacement.Epoch<=a.Epoch {t.Fatalf("ABA epoch: %v",err)}
    if !errors.Is(r.Check(a),ErrTargetStale) {t.Fatal("reused ref accepted old epoch")}
    if err=r.Rotate(8);err!=nil {t.Fatal(err)}
    if !errors.Is(r.Check(replacement),ErrTargetStale) {t.Fatal("old producer incarnation survived")}
    again,err:=r.BindTrustedRef(refA)
    if err!=nil || again.Generation!=8 || again.Epoch<=replacement.Epoch {t.Fatal("rotation broke monotonic epochs")}
    if err=r.Rotate(8);!errors.Is(err,ErrTargetStale) {t.Fatal("replayed generation accepted")}
    if err=r.Rotate(7);!errors.Is(err,ErrTargetStale) {t.Fatal("decreasing generation accepted")}
}
func TestTargetRegistryCrossSessionAndDesktopDenials(t *testing.T) {
    r,_:=NewTargetRegistry("session-A","desktop-A","source-A",3)
    a,_:=r.BindTrustedRef(refA)
    variants:=[]TargetStamp{
        {Session:"other",Desktop:a.Desktop,Producer:a.Producer,Generation:a.Generation,Ref:a.Ref,Epoch:a.Epoch},
        {Session:a.Session,Desktop:"other",Producer:a.Producer,Generation:a.Generation,Ref:a.Ref,Epoch:a.Epoch},
        {Session:a.Session,Desktop:a.Desktop,Producer:"other",Generation:a.Generation,Ref:a.Ref,Epoch:a.Epoch},
        {Session:a.Session,Desktop:a.Desktop,Producer:a.Producer,Generation:a.Generation+1,Ref:a.Ref,Epoch:a.Epoch},
        {Session:a.Session,Desktop:a.Desktop,Producer:a.Producer,Generation:a.Generation,Ref:refB,Epoch:a.Epoch},
        {Session:a.Session,Desktop:a.Desktop,Producer:a.Producer,Generation:a.Generation,Ref:a.Ref,Epoch:a.Epoch+1},
    }
    for i,v:=range variants {
        if !errors.Is(r.Check(v),ErrTargetStale) {t.Fatalf("mutated field %d accepted",i)}
        if !errors.Is(r.Revoke(v),ErrTargetStale) {t.Fatalf("mutated revoke %d accepted",i)}
    }
    if err:=r.Check(a);err!=nil {t.Fatalf("valid stamp lost: %v",err)}
}
func TestTargetRegistryMalformedAndIndependentRefs(t *testing.T) {
    for _,x:=range []uint64{0} {
        if _,err:=NewTargetRegistry("s","d","p",x);!errors.Is(err,ErrTargetInvalid){t.Fatal("zero generation accepted")}
    }
    r,_:=NewTargetRegistry("session","desktop","producer",1)
    for _,s:=range []string{"", "123", "HWND:0x00", "../outside", "has spaces and personal text"} {
        if _,err:=r.BindTrustedRef(s);!errors.Is(err,ErrTargetInvalid){t.Fatalf("bad ref accepted: %q",s)}
    }
    a,err:=r.BindTrustedRef(refA);if err!=nil {t.Fatal(err)}
    b,err:=r.BindTrustedRef(refB);if err!=nil || b.Epoch<=a.Epoch {t.Fatal("independent target stamp failure")}
    if r.Revoke(a)!=nil || r.Check(b)!=nil {t.Fatal("revoking A affected B")}
}
