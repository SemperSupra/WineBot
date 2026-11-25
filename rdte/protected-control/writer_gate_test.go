//go:build linux

package main

import (
 "errors"
 "os"
 "os/exec"
 "path/filepath"
 "syscall"
 "testing"
 "time"
)

func TestWriterGateSerializesAndFences(t *testing.T){
 root:=lifecycleTestRoot(t);uid:=uint32(os.Geteuid())
 if err:=lifecycleProvision(root,uid);err!=nil{t.Fatal(err)}
 populated:=false
 g,err:=reserveWriterGate(root,uid,0,func()(bool,error){return populated,nil})
 if err!=nil{t.Fatal(err)}
 calls:=0
 if err=g.launch(func()error{
  calls++
  if _,err:=lifecycleTransition(root,uid,1,"quarantine",g.scope,scopeEmptyProof{},nil);err==nil{
   t.Error("independent transition during dispatch")
  }
  s,err:=lifecycleRead(root,uid)
  if err!=nil || s.Phase!="RUNNING"{t.Error("intent absent before dispatch")}
  populated=true
  return nil
 });err!=nil{t.Fatal(err)}
 if err=g.launch(func()error{calls++;return nil});err==nil{t.Fatal("replay accepted")}
 if calls!=1{t.Fatal("duplicate dispatch")}
 if err=g.stopAndReconcile();err==nil{t.Fatal("populated scope released")}
 if _,err=reserveWriterGate(root,uid,1,func()(bool,error){return false,nil});err==nil{t.Fatal("replacement admitted")}
 populated=false
 if err=g.stopAndReconcile();err!=nil{t.Fatal(err)}
 if err=g.stopAndReconcile();err==nil{t.Fatal("retired handle accepted")}
 if _,err=reserveWriterGate(root,uid,1,func()(bool,error){return false,nil});err!=nil{t.Fatal(err)}
}

func TestWriterGateAmbiguousDispatchNeverRetries(t *testing.T){
 root:=lifecycleTestRoot(t);uid:=uint32(os.Geteuid())
 if err:=lifecycleProvision(root,uid);err!=nil{t.Fatal(err)}
 g,err:=reserveWriterGate(root,uid,0,func()(bool,error){return false,nil})
 if err!=nil{t.Fatal(err)}
 if err=g.launch(func()error{return errors.New("ambiguous completion")});err==nil{t.Fatal("expected failure")}
 if err=g.launch(func()error{t.Error("replayed dispatch");return nil});err==nil{t.Fatal("replay admitted")}
 if err=g.stopAndReconcile();err==nil{t.Fatal("ambiguous generation released")}
 s,err:=lifecycleRead(root,uid)
 if err!=nil || s.Phase!="QUARANTINED"{t.Fatal("not quarantined",err)}
 if _,err=reserveWriterGate(root,uid,1,func()(bool,error){return false,nil});err==nil{t.Fatal("restart admitted")}
}

func TestWriterGateRealContainedLaunch(t *testing.T){
 if os.Getenv("WINEBOT_REAL_WRITER_GATE")!="1"{t.Skip("dedicated disposable runner only")}
 if os.Geteuid()!=0{t.Fatal("fixture requires root")}
 root:=lifecycleTestRoot(t)
 if err:=lifecycleProvision(root,0);err!=nil{t.Fatal(err)}
 scope,err:=os.MkdirTemp("/sys/fs/cgroup","winebot-gate-fixture-")
 if err!=nil{t.Fatal(err)}
 defer os.Remove(scope)
 nested:=filepath.Join(scope,"nested")
 if err=os.Mkdir(nested,0700);err!=nil{t.Fatal(err)}
 defer os.Remove(nested)
 dir,err:=os.Open(scope)
 if err!=nil{t.Fatal(err)}
 defer dir.Close()
 sub,err:=os.Open(nested)
 if err!=nil{t.Fatal(err)}
 defer sub.Close()
 id,err:=cgroupID(dir)
 if err!=nil{t.Fatal(err)}
 g,err:=newWriterGate(root,0,0,dir,id)
 if err!=nil{t.Fatal(err)}
 child:=exec.Command("/bin/sleep","30")
 child.SysProcAttr=&syscall.SysProcAttr{UseCgroupFD:true,CgroupFD:int(sub.Fd())}
 if err=g.launch(child.Start);err!=nil{t.Fatal("atomic fixture placement unsupported or failed",err)}
 done:=make(chan error,1)
 go func(){done<-child.Wait()}()
 reaped:=false
 defer func(){
  if !reaped{_ = child.Process.Kill();select{case <-done:case <-time.After(5*time.Second):t.Error("cleanup timeout")}}
 }()
 if err=g.stopAndReconcile();err==nil{t.Fatal("live nested child released")}
 if err=killCgroupFixture(dir,id);err!=nil{t.Fatal(err)}
 select{
 case err=<-done:
  reaped=true
  ee,ok:=err.(*exec.ExitError)
  if !ok || ee.Sys().(syscall.WaitStatus).Signal()!=syscall.SIGKILL{t.Fatal("fixture not killed")}
 case <-time.After(5*time.Second):t.Fatal("reap timeout")
 }
 deadline:=time.Now().Add(5*time.Second)
 for{
  p,err:=cgroupPopulated(dir,id)
  if err!=nil{t.Fatal(err)}
  if !p{break}
  if time.Now().After(deadline){t.Fatal("scope remains populated")}
  time.Sleep(10*time.Millisecond)
 }
 if err=g.stopAndReconcile();err!=nil{t.Fatal(err)}
 if err=os.Remove(nested);err!=nil{t.Fatal(err)}
 if err=os.Remove(scope);err!=nil{t.Fatal(err)}
}
