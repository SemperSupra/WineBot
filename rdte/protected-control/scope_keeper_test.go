//go:build linux

package main

import (
 "os"
 "os/exec"
 "path/filepath"
 "strconv"
 "syscall"
 "testing"
 "time"
)

func TestScopeKeeperSupervisorChild(t *testing.T){
 if os.Getenv("WINEBOT_KEEPER_CHILD")!="1"{return}
 dir:=os.NewFile(3,"trusted fixture scope")
 if dir==nil{t.Fatal("missing scope descriptor")}
 defer dir.Close()
 id,err:=cgroupID(dir)
 if err!=nil{t.Fatal(err)}
 gnum,err:=strconv.ParseInt(os.Getenv("WINEBOT_KEEPER_GENERATION"),10,64)
 if err!=nil{t.Fatal(err)}
 g:=&writerGate{root:os.Getenv("WINEBOT_KEEPER_ROOT"),uid:0,
  generation:gnum,scope:os.Getenv("WINEBOT_KEEPER_SCOPE"),
  observe:func()(bool,error){return cgroupPopulated(dir,id)}}
 child:=exec.Command("/bin/sleep","30")
 child.SysProcAttr=&syscall.SysProcAttr{UseCgroupFD:true,CgroupFD:int(dir.Fd())}
 if err=g.launch(child.Start);err!=nil{t.Fatal(err)}
 // Do not reap the deliberately surviving fixture. The independent trusted
 // parent observes and drains its fresh synthetic cgroup.
 if err=syscall.Kill(os.Getpid(),syscall.SIGKILL);err!=nil{t.Fatal(err)}
 select{}
}

func TestScopeKeeperRealSupervisorDeath(t *testing.T){
 if os.Getenv("WINEBOT_REAL_SCOPE_KEEPER")!="1"{t.Skip("disposable hosted Linux only")}
 if os.Geteuid()!=0{t.Fatal("fixture requires root")}
 root:=lifecycleTestRoot(t)
 if err:=lifecycleProvision(root,0);err!=nil{t.Fatal(err)}
 scope,err:=os.MkdirTemp("/sys/fs/cgroup","winebot-keeper-fixture-")
 if err!=nil{t.Fatal(err)}
 defer os.Remove(scope)
 dir,err:=os.Open(scope)
 if err!=nil{t.Fatal(err)}
 defer dir.Close()
 id,err:=cgroupID(dir)
 if err!=nil{t.Fatal(err)}
 // Only the freshly created test scope is ever eligible for cleanup.
 defer func(){_ = killCgroupFixture(dir,id)}()
 g,err:=newWriterGate(root,0,0,dir,id)
 if err!=nil{t.Fatal(err)}
 bad:=id;bad.Inode^=1
 if _,err=retainScope(g,dir,bad);err==nil{t.Fatal("bad scope identity admitted")}
 k,err:=retainScope(g,dir,id)
 if err!=nil{t.Fatal(err)}
 defer k.close()
 if fd,_,e:=syscall.Syscall(syscall.SYS_FCNTL,k.dir.Fd(),uintptr(syscall.F_GETFD),0);e!=0 || fd&syscall.FD_CLOEXEC==0{
  t.Fatal("keeper descriptor not close-on-exec")
 }
 cmd:=exec.Command(os.Args[0],"-test.run=^TestScopeKeeperSupervisorChild$","-test.timeout=10s")
 cmd.ExtraFiles=[]*os.File{dir}
 cmd.Env=append(os.Environ(),"WINEBOT_KEEPER_CHILD=1",
  "WINEBOT_KEEPER_ROOT="+root,"WINEBOT_KEEPER_GENERATION=1",
  "WINEBOT_KEEPER_SCOPE="+g.scope)
 err=cmd.Run()
 ee,ok:=err.(*exec.ExitError)
 if !ok || ee.Sys().(syscall.WaitStatus).Signal()!=syscall.SIGKILL{t.Fatal("supervisor not killed",err)}
 // The original gate is deliberately not reused for recovery.
 p,err:=k.quarantineAndObserve()
 if err!=nil || !p{t.Fatal("surviving guest not detected",err)}
 if _,err=reserveWriterGate(root,0,1,func()(bool,error){return false,nil});err==nil{t.Fatal("replacement admitted")}
 if err=killCgroupFixture(dir,id);err!=nil{t.Fatal(err)}
 deadline:=time.Now().Add(5*time.Second)
 for{
  p,err=k.quarantineAndObserve()
  if err!=nil{t.Fatal(err)}
  if !p{break}
  if time.Now().After(deadline){t.Fatal("fixture failed to drain")}
  time.Sleep(10*time.Millisecond)
 }
 s,err:=lifecycleRead(root,0)
 if err!=nil || s.Phase!="QUARANTINED"{t.Fatal("empty scope released ambiguous generation",err)}
 if _,err=reserveWriterGate(root,0,1,func()(bool,error){return false,nil});err==nil{t.Fatal("replacement admitted after empty observation")}
 k.generation++
 if _,err=k.quarantineAndObserve();err==nil{t.Fatal("stale custody accepted")}
 k.generation--
 k.close()
 if _,err=k.quarantineAndObserve();err==nil{t.Fatal("lost custody accepted")}
 if err=os.Remove(scope);err!=nil{t.Fatal(err)}
}

func TestScopeKeeperLostCustodyRefuses(t *testing.T){
 k:=&scopeKeeper{root:filepath.Join(t.TempDir(),"absent")}
 if _,err:=k.quarantineAndObserve();err==nil{t.Fatal("lost custody accepted")}
}
