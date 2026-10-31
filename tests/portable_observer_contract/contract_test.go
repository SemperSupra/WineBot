// SPDX-License-Identifier: MIT
package observercontract

import (
    "encoding/json"
    "errors"
    "fmt"
    "reflect"
    "testing"
)

func record(kind string, seq int) []byte {
    return []byte(fmt.Sprintf("{\"schema\":\"%s\",\"kind\":\"%s\",\"sequence\":%d}\n",RawContract,kind,seq))
}
func frames(t *testing.T, runtime string, events [][]byte) []Frame {
    t.Helper()
    cap, err := UnverifiedCapabilities(runtime)
    if err != nil {t.Fatal(err)}
    if cap.Runtime!=runtime || cap.Contract!=Contract || !cap.FixtureScoped {t.Fatal("bad runtime capability declaration")}
    for _,v:=range cap.Features {
        if v!="unverified" {t.Fatal("unqualified runtime promoted a capability")}
    }
    adapter,err:=NewAdapter("test-incarnation")
    if err!=nil {t.Fatal(err)}
    var normalized []Frame
    for _,b:=range events {
        f,e:=adapter.Consume(b)
        if e!=nil {t.Fatal(e)}
        normalized=append(normalized,f)
    }
    return normalized
}
func TestSameClientInterfaceWindowsAndWine(t *testing.T) {
    events:=[][]byte{
        record("ready",0),record("create",1),record("show",2),
        record("location",3),record("hide",4),record("destroy",5),
    }
    native:=frames(t,"windows",events)
    wine:=frames(t,"wine",events)
    if !reflect.DeepEqual(native,wine) {t.Fatal("Windows and Wine events have different normalized consumer semantics")}
    want:=[]string{"ready","window.created","window.shown","window.location_changed","window.hidden","window.destroyed"}
    for i,v:=range native {
        got:=v.Kind
        if i==0 {got=v.Status}
        if got!=want[i] {t.Fatalf("normalized semantic mismatch at %d: %s",i,got)}
    }
    if _,err:=UnverifiedCapabilities("unknown");!errors.Is(err,ErrInvalid){t.Fatal("unsupported runtime advertised capabilities")}
}
func TestGapBecomesExplicitAndTerminal(t *testing.T) {
    a,_:=NewAdapter("test")
    if _,err:=a.Consume(record("ready",0));err!=nil {t.Fatal(err)}
    got,err:=a.Consume(record("show",2))
    if !errors.Is(err,ErrGap) || got.Status!="gap" {t.Fatal("missing events accepted without gap report")}
    if _,err:=a.Consume(record("location",3));!errors.Is(err,ErrTerminated){t.Fatal("gap stream remained usable")}
}
func TestOverflowBoundedAndTerminal(t *testing.T) {
    a,_:=NewAdapter("test")
    if _,err:=a.Consume(record("ready",0));err!=nil {t.Fatal(err)}
    for i:=1;i<=128;i++ {
        if _,err:=a.Consume(record("location",i));err!=nil {t.Fatalf("valid event %d: %v",i,err)}
    }
    got,err:=a.Consume(record("overflow",129))
    if err!=nil || got.Status!="overflow" || got.Sequence!=129 {t.Fatal("incorrect overflow semantics")}
    if _,err:=a.Consume(record("create",130));!errors.Is(err,ErrTerminated){t.Fatal("events after overflow accepted")}
}
func TestPrivacySchemaAndMalformedInputs(t *testing.T) {
    invalid:=[][]byte{
        nil,[]byte("not-json"),[]byte("{"),
        []byte(fmt.Sprintf("{\"schema\":\"%s\",\"kind\":\"ready\"}",RawContract)), // missing sequence
        []byte(fmt.Sprintf("{\"schema\":\"%s\",\"sequence\":0}",RawContract)), // missing kind
        []byte(fmt.Sprintf("{\"schema\":\"%s\",\"kind\":\"ready\",\"sequence\":0,\"title\":\"secret\"}",RawContract)),
        []byte(fmt.Sprintf("{\"schema\":\"%s\",\"kind\":\"create\",\"sequence\":true}",RawContract)),
        []byte(fmt.Sprintf("{\"schema\":\"%s\",\"kind\":\"ready\",\"sequence\":0}{\"other\":1}",RawContract)),
        []byte{0xff,0xfe},
    }
    for i,line:=range invalid {
        a,_:=NewAdapter("test")
        if _,err:=a.Consume(line);!errors.Is(err,ErrInvalid){t.Fatalf("unsafe raw input %d accepted: %v",i,err)}
    }
}
func TestNoFalseSupportOrEventFabrication(t *testing.T){
    win,_:=UnverifiedCapabilities("windows")
    wine,_:=UnverifiedCapabilities("wine")
    // Runtime identity is discoverable; portable event grammar is the same.
    if win.Runtime==wine.Runtime || !reflect.DeepEqual(win.Features,wine.Features) {t.Fatal("capability independence/shape failure")}
    a,_:=NewAdapter("test")
    if _,err:=a.Consume(record("ready",0));err!=nil{t.Fatal(err)}
    f,err:=a.Consume(record("destroy",1))
    if err!=nil || f.Kind!="window.destroyed" {t.Fatal("no local fabrication?")}
    if f.Kind=="window.location_changed" {t.Fatal("missing location event was fabricated")}
    b,_:=json.Marshal(f)
    for _,s:=range []string{"hwnd","title","path","pid"} {
        if containsString(string(b),s){t.Fatal("sensitive field leaked")}
    }
}
func containsString(s, sub string) bool {
    for i:=0;i+len(sub)<=len(s);i++ {if s[i:i+len(sub)]==sub{return true}}
    return false
}
