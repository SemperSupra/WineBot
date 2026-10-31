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
 for _,forbidden:=range []string{"hwnd","pid","title","target_ref","target_epoch","action"} {
  if strings.Contains(strings.ToLower(string(blob)),forbidden) {t.Fatalf("sensitive field leaked: %s",forbidden)}
 }
}
func TestWinInspectBridgeGapRequiresSnapshot(t *testing.T) {
 f,_:=NewFanout(1)
 b,_:=NewReadOnlyBridge(f,"wininspect")
 defer b.Close()
 for i:=0;i<3;i++ {_=f.Publish(Frame{Contract:Contract,Stream:"s",Source:Source,Sequence:i,Status:"observed"})}
 if _,err:=b.Poll(1);!errors.Is(err,ErrReinspectionRequired) {t.Fatalf("expected broad reinspection: %v",err)}
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
