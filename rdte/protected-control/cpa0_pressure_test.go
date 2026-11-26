//go:build linux

package main

import (
 "os"
 "os/exec"
 "path/filepath"
 "runtime"
 "strconv"
 "strings"
 "syscall"
 "testing"
 "time"
)

// Synthetic, bounded child; never accepts a target or a resource size.
func TestCPA0PressureChild(t *testing.T){
 switch os.Getenv("WINEBOT_CPA0_CHILD"){
 case "cpu":
  deadline:=time.Now().Add(20*time.Second)
  for time.Now().Before(deadline){}
 case "memory":
  blocks:=make([][]byte,0,128)
  for i:=0;i<128;i++{
   b:=make([]byte,1<<20)
   for p:=0;p<len(b);p+=4096{b[p]=1}
   blocks=append(blocks,b)
  }
  runtime.KeepAlive(blocks)
  t.Fatal("bounded allocation unexpectedly survived")
 }
}

func cpaCounter(t *testing.T,scope,file,key string)uint64{
 t.Helper()
 b,err:=os.ReadFile(filepath.Join(scope,file))
 if err!=nil{t.Fatal("controller observation failed",err)}
 for _,line:=range strings.Split(string(b),"\n"){
  f:=strings.Fields(line)
  if len(f)==2 && f[0]==key{
   n,err:=strconv.ParseUint(f[1],10,64)
   if err!=nil{t.Fatal("invalid counter")}
   return n
  }
 }
 t.Fatal("required counter absent")
 return 0
}

func TestCPA0DurableStopPressure(t *testing.T){
 if os.Getenv("WINEBOT_REAL_CPA0_PRESSURE")!="1"{t.Skip("disposable hosted runner only")}
 if os.Geteuid()!=0{t.Fatal("root fixture required")}
 for _,mode:=range []string{"cpu","memory"}{
  t.Run(mode,func(t *testing.T){
   root:=lifecycleTestRoot(t)
   if err:=lifecycleProvision(root,0);err!=nil{t.Fatal(err)}
   scope,err:=os.MkdirTemp("/sys/fs/cgroup","winebot-cpa0-pressure-")
   if err!=nil{t.Fatal(err)}
   defer os.Remove(scope)
   dir,err:=os.Open(scope)
   if err!=nil{t.Fatal(err)}
   defer dir.Close()
   id,err:=cgroupID(dir)
   if err!=nil{t.Fatal(err)}
   limits:=map[string]string{"cpu.max":"20000 100000","memory.max":"50331648","memory.swap.max":"0","pids.max":"32"}
   for file,value:=range limits{
    p:=filepath.Join(scope,file)
    if err=os.WriteFile(p,[]byte(value),0600);err!=nil{t.Fatal("required controller unavailable",err)}
    b,err:=os.ReadFile(p)
    if err!=nil || strings.TrimSpace(string(b))!=value{t.Fatal("effective leaf cap mismatch",err)}
   }
   g,err:=newWriterGate(root,0,0,dir,id)
   if err!=nil{t.Fatal(err)}
   e,err:=newEmergencyDispatch(g)
   if err!=nil{t.Fatal(err)}
   // Copy test executable to an explicitly disposable, traversable directory
   // so UID 1000 need not traverse the runner's original build path.
   binDir,err:=os.MkdirTemp("/tmp","winebot-cpa0-bin-")
   if err!=nil{t.Fatal(err)}
   defer os.RemoveAll(binDir)
   if err=os.Chmod(binDir,0755);err!=nil{t.Fatal(err)}
   b,err:=os.ReadFile(os.Args[0])
   if err!=nil{t.Fatal(err)}
   bin:=filepath.Join(binDir,"fixture")
   if err=os.WriteFile(bin,b,0755);err!=nil{t.Fatal(err)}
   child:=exec.Command(bin,"-test.run=^TestCPA0PressureChild$","-test.timeout=25s")
   child.Env=[]string{"WINEBOT_CPA0_CHILD="+mode,"GOMAXPROCS=1"}
   child.SysProcAttr=&syscall.SysProcAttr{UseCgroupFD:true,CgroupFD:int(dir.Fd()),Credential:&syscall.Credential{Uid:1000,Gid:1000,Groups:[]uint32{}}}
   beforeOOM:=cpaCounter(t,scope,"memory.events","oom_kill")
   beforeCPU:=cpaCounter(t,scope,"cpu.stat","nr_throttled")
   if err=g.launch(child.Start);err!=nil{t.Fatal("atomic placement failed",err)}
   done:=make(chan error,1)
   go func(){done<-child.Wait()}()
   reaped:=false
   defer func(){
    if !reaped{
     _=killCgroupFixture(dir,id)
     select{case <-done:case <-time.After(5*time.Second):t.Error("fixture cleanup timeout")}
    }
   }()
   if mode=="cpu"{
    deadline:=time.Now().Add(5*time.Second)
    for cpaCounter(t,scope,"cpu.stat","nr_throttled")<=beforeCPU{
     if time.Now().After(deadline){t.Fatal("throttling not observed")}
     time.Sleep(50*time.Millisecond)
    }
    if p,err:=cgroupPopulated(dir,id);err!=nil || !p{t.Fatal("pressure scope not live",err)}
    receipt:=make(chan error,1)
    go func(){_,err:=e.requestPersistentStop();receipt<-err}()
    select{
    case err:=<-receipt:if err!=nil{t.Fatal("durable STOP failed",err)}
    case <-time.After(3*time.Second):t.Fatal("durable STOP receipt exceeded bound")
    }
    if p,err:=cgroupPopulated(dir,id);err!=nil || !p{t.Fatal("STOP receipt confused with actual termination",err)}
    if err=killCgroupFixture(dir,id);err!=nil{t.Fatal(err)}
    t.Log("CPA0_PRESSURE stage=cpu_throttled_durable_stop_and_scoped_kill")
   }
   select{
   case err=<-done:
    reaped=true
    ee,ok:=err.(*exec.ExitError)
    if !ok || ee.Sys().(syscall.WaitStatus).Signal()!=syscall.SIGKILL{t.Fatal("expected SIGKILL")}
   case <-time.After(15*time.Second):t.Fatal("fixture not terminated")
   }
   if mode=="memory"{
    if cpaCounter(t,scope,"memory.events","oom_kill")<=beforeOOM{t.Fatal("OOM kill not independently observed")}
    s,err:=lifecycleRead(root,0)
    if err!=nil || s.Phase!="RUNNING"{t.Fatal("OOM incorrectly represented as recovery",err)}
    if _,err=e.requestPersistentStop();err!=nil{t.Fatal(err)}
    t.Log("CPA0_PRESSURE stage=bounded_oom_kill_observed_no_automatic_release")
   }
   deadline:=time.Now().Add(5*time.Second)
   for{
    p,err:=cgroupPopulated(dir,id)
    if err!=nil{t.Fatal(err)}
    if !p{break}
    if time.Now().After(deadline){t.Fatal("scope still populated")}
    time.Sleep(10*time.Millisecond)
   }
   if err=g.stopAndReconcile();err==nil{t.Fatal("durable STOP released")}
   s,err:=lifecycleRead(root,0)
   if err!=nil || s.Phase!="QUARANTINED"{t.Fatal("quarantine missing",err)}
   if _,err=reserveWriterGate(root,0,g.generation,func()(bool,error){return false,nil});err==nil{t.Fatal("replacement admitted")}
   t.Log("CPA0_PRESSURE stage=empty_scope_remains_quarantined")
  })
 }
}
