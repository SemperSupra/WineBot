//go:build linux

package main

import (
 "context"
 "errors"
 "os"
 "os/exec"
 "path/filepath"
 "strconv"
 "testing"
 "time"
)

func emergencyFixture(t *testing.T)(*emergencyDispatch,string){
 t.Helper()
 root:=lifecycleTestRoot(t);uid:=uint32(os.Geteuid())
 if err:=lifecycleProvision(root,uid);err!=nil{t.Fatal(err)}
 g,err:=reserveWriterGate(root,uid,0,func()(bool,error){return false,nil})
 if err!=nil{t.Fatal(err)}
 e,err:=newEmergencyDispatch(g)
 if err!=nil{t.Fatal(err)}
 return e,root
}

func TestEmergencyStopBeforeSubmission(t *testing.T){
 e,root:=emergencyFixture(t)
 s:=e.requestStop()
 if !s.StopRequested || s.Submitted || s.InFlight || s.Returned{t.Fatal(s)}
 if err:=e.run(func(context.Context)error{t.Error("dispatch after STOP");return nil});err==nil{
  t.Fatal("dispatch admitted")
 }
 record,err:=lifecycleRead(root,uint32(os.Geteuid()))
 if err!=nil || record.Phase!="RESERVED"{t.Fatal("request falsely represented durable quarantine",err)}
}

func TestEmergencyStopWhileJournalLocked(t *testing.T){
 e,root:=emergencyFixture(t)
 entered:=make(chan struct{})
 canceled:=make(chan struct{})
 release:=make(chan struct{})
 done:=make(chan error,1)
 defer func(){
  close(release)
  select{case <-done:case <-time.After(5*time.Second):t.Error("worker cleanup timeout")}
 }()
 go func(){done<-e.run(func(ctx context.Context)error{
  close(entered)
  <-ctx.Done()
  close(canceled)
  <-release
  return ctx.Err()
 })}()
 select{case <-entered:case <-time.After(5*time.Second):t.Fatal("dispatch not entered")}
 if d,l,err:=acquire(root,uint32(os.Geteuid()));err==nil{
  l.Close();d.Close();t.Fatal("ordinary lock not held")
 }
 receipts:=make(chan emergencyStatus,1)
 go func(){receipts<-e.requestStop()}()
 select{
 case s:=<-receipts:
  if !s.StopRequested || !s.InFlight || s.Returned{t.Fatal(s)}
 case <-time.After(2*time.Second):t.Fatal("STOP blocked behind ordinary lock")
 }
 select{case <-canceled:case <-time.After(2*time.Second):t.Fatal("cancel not delivered")}
 if !e.status().InFlight{t.Fatal("cancel falsely reported termination")}
 if err:=e.run(func(context.Context)error{return nil});err==nil{t.Fatal("replay admitted")}
 // Deferred release lets the worker finish even on assertion failure.
}

func TestEmergencyLateCompletionRemainsAmbiguous(t *testing.T){
 e,_:=emergencyFixture(t)
 entered:=make(chan struct{})
 release:=make(chan struct{})
 done:=make(chan error,1)
 released:=false
 defer func(){if !released{close(release)}}()
 go func(){done<-e.run(func(context.Context)error{
  close(entered)
  <-release
  // Deliberately ignore cancellation: external completion can arrive late.
  return nil
 })}()
 select{case <-entered:case <-time.After(5*time.Second):t.Fatal("dispatch not entered")}
 s:=e.requestStop()
 if !s.InFlight || !s.StopRequested{t.Fatal(s)}
 close(release);released=true
 select{
 case err:=<-done:if err!=nil{t.Fatal(err)}
 case <-time.After(5*time.Second):t.Fatal("worker not returned")
 }
 s=e.status()
 if !s.Returned || !s.StopRequested || !s.Ambiguous || s.InFlight{t.Fatal(s)}
 if err:=e.run(func(context.Context)error{return nil});err==nil{t.Fatal("second launch admitted")}
}

func TestEmergencyDispatchErrorAndPanic(t *testing.T){
 e,_:=emergencyFixture(t)
 if err:=e.run(func(context.Context)error{return errors.New("unknown effect")});err==nil{t.Fatal("expected error")}
 if s:=e.status();!s.Ambiguous || !s.Returned || s.InFlight{t.Fatal(s)}
 p,_:=emergencyFixture(t)
 func(){
  defer func(){if recover()==nil{t.Error("panic swallowed")}}()
  _=p.run(func(context.Context)error{panic("fixture")})
 }()
 if s:=p.status();!s.Ambiguous || !s.Returned || s.InFlight{t.Fatal(s)}
}

func TestEmergencyExternalStopConsumption(t *testing.T){
 for _,mode:=range []string{"independent_requester","corrupt","foreign"}{
  t.Run(mode,func(t *testing.T){
   e,root:=emergencyFixture(t)
   g:=e.gate
   entered,canceled,release:=make(chan struct{}),make(chan struct{}),make(chan struct{})
   done:=make(chan error,1)
   defer func(){
    close(release)
    select{case <-done:case <-time.After(5*time.Second):t.Error("worker cleanup timeout")}
   }()
   go func(){done<-e.run(func(ctx context.Context)error{
    close(entered)
    <-ctx.Done()
    close(canceled)
    <-release
    return ctx.Err()
   })}()
   select{case <-entered:case <-time.After(5*time.Second):t.Fatal("dispatch not entered")}
   switch mode{
   case "independent_requester":
    ctx,cancel:=context.WithTimeout(context.Background(),5*time.Second)
    defer cancel()
    cmd:=exec.CommandContext(ctx,os.Args[0],"-test.run=^TestDurableStopChild$","-test.timeout=4s")
    cmd.Env=append(os.Environ(),"WINEBOT_STOP_CHILD=1","WINEBOT_STOP_ROOT="+root,
     "WINEBOT_STOP_GENERATION="+strconv.FormatInt(g.generation,10),"WINEBOT_STOP_SCOPE="+g.scope)
    if err:=cmd.Run();err!=nil{t.Fatal("independent STOP failed",err)}
   case "corrupt":
    if err:=os.WriteFile(filepath.Join(root,durableStopName),[]byte("{"),0600);err!=nil{t.Fatal(err)}
   case "foreign":
    b,err:=lifecycleBytes(lifecycleRecord{Schema:lifecycleSchema,Generation:g.generation+1,Phase:"QUARANTINED",Scope:"foreign"})
    if err!=nil{t.Fatal(err)}
    if err=os.WriteFile(filepath.Join(root,durableStopName),b,0600);err!=nil{t.Fatal(err)}
   }
   select{case <-canceled:case <-time.After(3*time.Second):t.Fatal("external STOP not consumed")}
   s:=e.status()
   if !s.StopRequested || !s.InFlight || s.Returned{t.Fatal("cancellation confused with termination",s)}
   if err:=e.run(func(context.Context)error{return nil});err==nil{t.Fatal("replay accepted")}
  })
 }
}

func TestEmergencyNoExternalStopNormalCompletion(t *testing.T){
 e,root:=emergencyFixture(t)
 if err:=e.run(func(ctx context.Context)error{
  select{case <-ctx.Done():return ctx.Err();case <-time.After(75*time.Millisecond):return nil}
 });err!=nil{t.Fatal(err)}
 s:=e.status()
 if s.StopRequested || s.Ambiguous || !s.Returned || s.InFlight{t.Fatal(s)}
 if r,err:=readDurableStop(root,e.gate.uid);err!=nil || r!=nil{t.Fatal("normal completion fabricated STOP",err)}
}
