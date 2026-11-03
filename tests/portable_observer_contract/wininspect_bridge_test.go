package observercontract

import (
 "encoding/json"
 "errors"
 "strings"
 "testing"
)

func TestWinInspectBridgeNoTargetLeak(t *testing.T) {
 f,_:=NewFanout(3)
 b,err:=NewReadOnlyBridge(f,"wininspect")
 if err!=nil {t.Fatal(err)}
 defer b.Close()
 _=f.Publish(Frame{Contract:Contract,Stream:"trusted-session",Source:Source,Sequence:1,Status:"observed",Kind:"window.created"})
 hints,err:=b.Poll(3)
 if err!=nil||len(hints)!=1||hints[0].Scope!="desktop" {t.Fatalf("%v %v",hints,err)}
 blob,_:=json.Marshal(hints)
 for _,forbidden:=range []string{"hwnd","pid","title","target_ref","target_epoch","action","cursor","reader"} {
  if strings.Contains(strings.ToLower(string(blob)),forbidden) {t.Fatalf("sensitive field leaked: %s",forbidden)}
 }
}
func TestWinInspectBridgeGapRequiresSnapshot(t *testing.T) {
 f,_:=NewFanout(1)
 b,_:=NewReadOnlyBridge(f,"wininspect")
 defer b.Close()
 for i:=0;i<3;i++ {_=f.Publish(Frame{Contract:Contract,Stream:"s",Source:Source,Sequence:i,Status:"observed"})}
 if _,err:=b.Poll(1);!errors.Is(err,ErrReinspectionRequired) {
  t.Fatalf("expected broad reinspection: %v",err)
 } else {
  var cause *ReinspectionError
  if !errors.As(err,&cause) || cause.Reason!="gap" {t.Fatalf("lost typed reader overrun cause: %v",err)}
 }
}
func TestWinInspectBridgeMultipleConsumers(t *testing.T) {
 f,_:=NewFanout(4)
 a,_:=NewReadOnlyBridge(f,"wininspect")
 b,_:=NewReadOnlyBridge(f,"automation")
 defer a.Close();defer b.Close()
 _=f.Publish(Frame{Contract:Contract,Stream:"s",Source:Source,Sequence:1,Status:"overflow"})
 h1,e1:=a.Poll(2);h2,e2:=b.Poll(2)
 if e1!=nil||e2!=nil||len(h1)!=1||len(h2)!=1||h1[0].Reason!="overflow"||h2[0].Reason!="overflow" {t.Fatalf("%v %v %v %v",h1,h2,e1,e2)}
}

func TestScopedWinInspectBridgeTypedTerminalFailures(t *testing.T) {
 type example struct {name string; status string; stream string; sequence int; kind string; reason string}
 examples:=[]example{
  {"producer_overflow","overflow","typed-stream",1,"","overflow"},
  {"unsupported","unsupported","typed-stream",1,"","unsupported"},
  {"sequence_gap","observed","typed-stream",2,"window.shown","gap"},
  {"replay","observed","typed-stream",0,"window.shown","replay"},
  {"wrong_stream","observed","previous-incarnation",1,"window.shown","stale_source"},
  {"invalid_event","observed","typed-stream",1,"window.not-a-real-event","invalid_event"},
 }
 for _,tc:=range examples {
  t.Run(tc.name,func(t *testing.T) {
   relay,err:=NewScopedRelay("typed-stream",Source,7,4)
   if err!=nil {t.Fatal(err)}
   if err:=relay.Accept(Frame{Contract:Contract,Stream:"typed-stream",Source:Source,Sequence:0,Status:"ready"});err!=nil {t.Fatal(err)}
   bridge,err:=relay.NewBridge("read-only-inspector")
   if err!=nil {t.Fatal(err)}
   defer bridge.Close()
   if err:=relay.Accept(Frame{Contract:Contract,Stream:tc.stream,Source:Source,Sequence:tc.sequence,Status:tc.status,Kind:tc.kind});!errors.Is(err,ErrRelayStale) {
    t.Fatalf("terminal failure incorrectly admitted: %v",err)
   }
   if _,err:=bridge.Poll(4);!errors.Is(err,ErrReinspectionRequired) {
    t.Fatalf("poisoned stream returned observations: %v",err)
   } else {
    var terminal *ReinspectionError
    if !errors.As(err,&terminal) || terminal.Reason!=tc.reason {
     t.Fatalf("terminal reason lost: got=%v expected=%q",err,tc.reason)
    }
    if err.Error()!="reinspection_required" {t.Fatal("unbounded error text")}
   }
   if _,err:=relay.NewBridge("other");!errors.Is(err,ErrRelayStale) {
    t.Fatalf("admitted new reader after termination: %v",err)
   }
  })
 }
}
