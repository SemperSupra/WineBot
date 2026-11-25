//go:build linux

package main

import (
 "context"
 "os"
 "os/exec"
 "path/filepath"
 "strconv"
 "testing"
 "time"
)

func TestDurableStopChild(t *testing.T){
 if os.Getenv("WINEBOT_STOP_CHILD")!="1"{return}
 g,err:=strconv.ParseInt(os.Getenv("WINEBOT_STOP_GENERATION"),10,64)
 if err!=nil{t.Fatal(err)}
 if err=requestDurableStop(os.Getenv("WINEBOT_STOP_ROOT"),uint32(os.Geteuid()),g,os.Getenv("WINEBOT_STOP_SCOPE"));err!=nil{t.Fatal(err)}
}

func TestDurableStopSurvivesRequesterExit(t *testing.T){
 e,root:=emergencyFixture(t)
 g:=e.gate
 cmd:=exec.Command(os.Args[0],"-test.run=^TestDurableStopChild$","-test.timeout=10s")
 cmd.Env=append(os.Environ(),"WINEBOT_STOP_CHILD=1","WINEBOT_STOP_ROOT="+root,
  "WINEBOT_STOP_GENERATION="+strconv.FormatInt(g.generation,10),"WINEBOT_STOP_SCOPE="+g.scope)
 if err:=cmd.Run();err!=nil{t.Fatal(err)}
 // A new handle has no in-memory STOP latch.
 restarted:=&writerGate{root:root,uid:g.uid,generation:g.generation,scope:g.scope,observe:func()(bool,error){return false,nil}}
 if err:=restarted.launch(func()error{t.Error("dispatch after durable STOP");return nil});err==nil{t.Fatal("launch admitted")}
 if err:=restarted.stopAndReconcile();err==nil{t.Fatal("STOP released")}
 if _,err:=reserveWriterGate(root,g.uid,g.generation,func()(bool,error){return false,nil});err==nil{t.Fatal("replacement admitted")}
 if err:=requestDurableStop(root,g.uid,g.generation,g.scope);err!=nil{t.Fatal("idempotent STOP failed",err)}
}

func TestDurableStopDuringDispatch(t *testing.T){
 e,root:=emergencyFixture(t)
 entered:=make(chan struct{})
 release:=make(chan struct{})
 done:=make(chan error,1)
 defer func(){
  close(release)
  select{case <-done:case <-time.After(5*time.Second):t.Error("worker cleanup timeout")}
 }()
 go func(){done<-e.run(func(context.Context)error{close(entered);<-release;return nil})}()
 select{case <-entered:case <-time.After(5*time.Second):t.Fatal("dispatch not entered")}
 receipts:=make(chan error,1)
 go func(){_,err:=e.requestPersistentStop();receipts<-err}()
 select{case err:=<-receipts:if err!=nil{t.Fatal(err)};case <-time.After(3*time.Second):t.Fatal("STOP blocked on dispatch")}
 s,err:=readDurableStop(root,e.gate.uid)
 if err!=nil || s==nil || s.Scope!=e.gate.scope{t.Fatal("STOP not persisted",err)}
 if !e.status().InFlight{t.Fatal("durable request confused with termination")}
}

func TestDurableStopDuringObservation(t *testing.T){
 e,_:=emergencyFixture(t)
 g:=e.gate
 g.observe=func()(bool,error){
  return false,requestDurableStop(g.root,g.uid,g.generation,g.scope)
 }
 if err:=g.stopAndReconcile();err==nil{t.Fatal("release raced STOP")}
 s,err:=lifecycleRead(g.root,g.uid)
 if err!=nil || s.Phase!="QUARANTINED"{t.Fatal("quarantine lost",err)}
}

func TestDurableStopCorruptionAndStaleTarget(t *testing.T){
 e,root:=emergencyFixture(t);g:=e.gate
 if err:=requestDurableStop(root,g.uid,g.generation,"wrong-scope");err==nil{t.Fatal("stale target accepted")}
 if s,err:=readDurableStop(root,g.uid);err!=nil || s!=nil{t.Fatal("stale request mutated STOP")}
 if err:=os.WriteFile(filepath.Join(root,durableStopName),[]byte("{"),0600);err!=nil{t.Fatal(err)}
 if err:=g.launch(func()error{t.Error("corrupt STOP admitted");return nil});err==nil{t.Fatal("corrupt STOP admitted")}
 if err:=g.stopAndReconcile();err==nil{t.Fatal("corrupt STOP released")}
}
