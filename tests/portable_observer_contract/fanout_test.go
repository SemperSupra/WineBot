package observercontract

import (
 "errors"
 "testing"
)

func TestFanoutIndependentCursors(t *testing.T) {
 f,_:=NewFanout(4)
 if err:=f.Subscribe("wininspect");err!=nil {t.Fatal(err)}
 if err:=f.Subscribe("agent");err!=nil {t.Fatal(err)}
 for i:=0;i<3;i++ {
  if err:=f.Publish(Frame{Contract:Contract,Stream:"fixture-1",Source:Source,Sequence:i,Status:"observed",Kind:"window.created"});err!=nil {t.Fatal(err)}
 }
 a,e:=f.Poll("wininspect",2)
 if e!=nil||len(a)!=2 {t.Fatalf("first cursor %v %v",a,e)}
 b,e:=f.Poll("agent",4)
 if e!=nil||len(b)!=3 {t.Fatalf("second cursor %v %v",b,e)}
 a,e=f.Poll("wininspect",4)
 if e!=nil||len(a)!=1||a[0].Sequence!=2 {t.Fatalf("cursor independence %v %v",a,e)}
}
func TestFanoutGapFailClosed(t *testing.T) {
 f,_:=NewFanout(2)
 _=f.Subscribe("slow")
 for i:=0;i<4;i++ {_=f.Publish(Frame{Contract:Contract,Stream:"fixture-1",Source:Source,Sequence:i,Status:"observed"})}
 if _,err:=f.Poll("slow",2);!errors.Is(err,ErrCursorGap){t.Fatalf("gap: %v",err)}
 f.Unsubscribe("slow")
 _=f.Subscribe("slow")
 frames,err:=f.Poll("slow",2)
 if err!=nil||len(frames)!=0 {t.Fatalf("fresh cursor: %v %v",frames,err)}
}
func TestFanoutInvalidAndDuplicate(t *testing.T) {
 if _,err:=NewFanout(0);!errors.Is(err,ErrInvalid){t.Fatal(err)}
 f,_:=NewFanout(1)
 if err:=f.Subscribe("a");err!=nil {t.Fatal(err)}
 if err:=f.Subscribe("a");!errors.Is(err,ErrCursorDuplicate){t.Fatal(err)}
 if err:=f.Publish(Frame{Contract:Contract,Stream:"s",Source:Source,Status:"actuate"});!errors.Is(err,ErrInvalid){t.Fatal(err)}
 if _,err:=f.Poll("unknown",1);!errors.Is(err,ErrCursorUnknown){t.Fatal(err)}
}
