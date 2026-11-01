// SPDX-License-Identifier: MIT
package observercontract

import (
  "errors"
  "encoding/json"
  "strings"
  "testing"
)

func scopedFrame(stream string,seq int,status,kind string) Frame {
  return Frame{Contract:Contract,Stream:stream,Source:Source,Sequence:seq,Status:status,Kind:kind}
}
func TestScopedRelayTwoIndependentConsumers(t *testing.T) {
  r,e:=NewScopedRelay("synthetic-stream-generation-1",Source,1,8)
  if e!=nil {t.Fatal(e)}
  if e=r.Accept(scopedFrame("synthetic-stream-generation-1",0,"ready",""));e!=nil {t.Fatal(e)}
  a,e:=r.NewBridge("wininspect")
  if e!=nil {t.Fatal(e)}
  b,e:=r.NewBridge("automation")
  if e!=nil {t.Fatal(e)}
  defer a.Close();defer b.Close()
  for i,k:=range []string{"window.created","window.shown","window.location_changed"} {
    if e=r.Accept(scopedFrame("synthetic-stream-generation-1",i+1,"observed",k));e!=nil {t.Fatal(e)}
  }
  left,e:=a.Poll(2)
  if e!=nil || len(left)!=2 {t.Fatalf("first poll %v %v",left,e)}
  right,e:=b.Poll(8)
  if e!=nil || len(right)!=3 {t.Fatalf("second poll %v %v",right,e)}
  rest,e:=a.Poll(8)
  if e!=nil || len(rest)!=1 || rest[0].Reason!="window.location_changed" {
    t.Fatalf("late cursor %v %v",rest,e)
  }
  blob,_:=json.Marshal(right)
  for _,secret:=range []string{"hwnd","pid","target_ref","target_epoch","principal","action"} {
    if strings.Contains(strings.ToLower(string(blob)),secret){t.Fatalf("forbidden field %s",secret)}
  }
}
func TestScopedRelayMixedStreamAndReplayFailClosed(t *testing.T) {
  variants:=[]Frame{
    scopedFrame("other-stream-generation",1,"observed","window.created"),
    scopedFrame("synthetic-stream-generation-1",3,"observed","window.created"),
    scopedFrame("synthetic-stream-generation-1",1,"observed","window.created"),
    scopedFrame("synthetic-stream-generation-1",2,"observed","unverified.kind"),
    scopedFrame("synthetic-stream-generation-1",2,"overflow",""),
  }
  for i,bad:=range variants {
    r,_:=NewScopedRelay("synthetic-stream-generation-1",Source,1,4)
    _=r.Accept(scopedFrame("synthetic-stream-generation-1",0,"ready",""))
    bridge,_:=r.NewBridge("wininspect")
    _=r.Accept(scopedFrame("synthetic-stream-generation-1",1,"observed","window.shown"))
    if !errors.Is(r.Accept(bad),ErrRelayStale) {t.Fatalf("case %d accepted",i)}
    if _,e:=bridge.Poll(4);!errors.Is(e,ErrReinspectionRequired) {t.Fatalf("case %d kept live cursor: %v",i,e)}
    if _,e:=r.NewBridge("later");!errors.Is(e,ErrRelayStale) {t.Fatal("reused poisoned relay")}
    bridge.Close()
  }
}
func TestScopedRelayRestartAndOverflow(t *testing.T) {
  old,_:=NewScopedRelay("stream-old-generation",Source,5,2)
  _=old.Accept(scopedFrame("stream-old-generation",0,"ready",""))
  slow,_:=old.NewBridge("slow")
  for i:=1;i<=3;i++ {_=old.Accept(scopedFrame("stream-old-generation",i,"observed","window.shown"))}
  if _,e:=slow.Poll(2);!errors.Is(e,ErrReinspectionRequired) {t.Fatalf("slow consumer loss: %v",e)}
  slow.Close()
  newer,_:=NewScopedRelay("stream-new-generation",Source,6,4)
  _=newer.Accept(scopedFrame("stream-new-generation",0,"ready",""))
  if e:=newer.Accept(scopedFrame("stream-old-generation",1,"observed","window.shown"));!errors.Is(e,ErrRelayStale) {t.Fatal("old stream accepted")}
  next,_:=NewScopedRelay("stream-new-generation-2",Source,7,4)
  _=next.Accept(scopedFrame("stream-new-generation-2",0,"ready",""))
  consumer,_:=next.NewBridge("new-reader")
  if e:=next.Accept(scopedFrame("stream-new-generation-2",1,"observed","window.shown"));e!=nil {t.Fatal(e)}
  hints,e:=consumer.Poll(4)
  if e!=nil || len(hints)!=1 {t.Fatalf("new stream restart %v %v",hints,e)}
  consumer.Close()
}
