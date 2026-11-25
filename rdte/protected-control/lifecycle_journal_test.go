//go:build linux

package main

import (
 "os"
 "os/exec"
 "path/filepath"
 "strconv"
 "syscall"
 "testing"
)

func lifecycleTestRoot(t *testing.T) string {
 t.Helper()
 root:=t.TempDir()
 if err:=os.Chmod(root,0700);err!=nil{t.Fatal(err)}
 return root
}

func lifecycleMust(t *testing.T,root string,g int64,event,scope string,p scopeEmptyProof) lifecycleRecord {
 t.Helper()
 s,err:=lifecycleTransition(root,uint32(os.Geteuid()),g,event,scope,p,nil)
 if err!=nil{t.Fatal(err)}
 return s
}

func TestLifecycleStrictTransitions(t *testing.T) {
 root:=lifecycleTestRoot(t);uid:=uint32(os.Geteuid())
 reject:=func(g int64,event,scope string,p scopeEmptyProof){
  t.Helper()
  if _,err:=lifecycleTransition(root,uid,g,event,scope,p,nil);err==nil{t.Fatal("unexpected admission")}
 }
 reject(0,"reserve","scope-a",scopeEmptyProof{})
 if err:=lifecycleProvision(root,uid);err!=nil{t.Fatal(err)}
 if err:=lifecycleProvision(root,uid);err==nil{t.Fatal("duplicate provision")}
 s:=lifecycleMust(t,root,0,"reserve","scope-a",scopeEmptyProof{})
 if s.Generation!=1 || s.Phase!="RESERVED"{t.Fatal(s)}
 reject(0,"launch_intent","scope-a",scopeEmptyProof{})
 reject(1,"reserve","scope-b",scopeEmptyProof{})
 reject(1,"launch_intent","scope-b",scopeEmptyProof{})
 lifecycleMust(t,root,1,"launch_intent","scope-a",scopeEmptyProof{})
 reject(1,"launch_intent","scope-a",scopeEmptyProof{})
 p:=scopeEmptyProof{1,"scope-a",true,true,true}
 reject(1,"reconcile","scope-a",p)
 lifecycleMust(t,root,1,"quarantine","scope-a",scopeEmptyProof{})
 for _,bad:=range []scopeEmptyProof{
  {0,"scope-a",true,true,true},{1,"scope-b",true,true,true},
  {1,"scope-a",false,true,true},{1,"scope-a",true,false,true},
  {1,"scope-a",true,true,false},
 }{reject(1,"reconcile","scope-a",bad)}
 s=lifecycleMust(t,root,1,"reconcile","scope-a",p)
 if s.Phase!="IDLE" || s.Generation!=1 || s.Scope!=""{t.Fatal(s)}
 lifecycleMust(t,root,1,"reserve","scope-b",scopeEmptyProof{})
 lifecycleMust(t,root,2,"quarantine","scope-b",scopeEmptyProof{})
 reject(2,"reconcile","scope-b",p)
}

func TestLifecycleRejectsCorruptAndMissingState(t *testing.T) {
 root:=lifecycleTestRoot(t);uid:=uint32(os.Geteuid())
 if err:=lifecycleProvision(root,uid);err!=nil{t.Fatal(err)}
 path:=filepath.Join(root,lifecycleName)
 for _,b:=range []string{
  "{",`{"schema":"winebot/writer-lifecycle/v1","generation":0,"generation":0,"phase":"IDLE","scope":""}`+"\n",
  `{"schema":"winebot/writer-lifecycle/v1","generation":0,"phase":"RUNNING","scope":"a"}`+"\n",
 }{
  if err:=os.WriteFile(path,[]byte(b),0600);err!=nil{t.Fatal(err)}
  if _,err:=lifecycleTransition(root,uid,0,"reserve","scope-a",scopeEmptyProof{},nil);err==nil{t.Fatal("corrupt state admitted")}
 }
 if err:=os.Remove(path);err!=nil{t.Fatal(err)}
 if _,err:=lifecycleTransition(root,uid,0,"reserve","scope-a",scopeEmptyProof{},nil);err==nil{t.Fatal("missing state admitted")}
 if _,err:=os.Stat(path);!os.IsNotExist(err){t.Fatal("missing state recreated")}
}

func TestLifecycleCrashChild(t *testing.T) {
 if os.Getenv("WINEBOT_TEST_CRASH_CHILD")!="1"{return}
 root:=os.Getenv("WINEBOT_TEST_ROOT");stage:=os.Getenv("WINEBOT_TEST_STAGE")
 g,err:=strconv.ParseInt(os.Getenv("WINEBOT_TEST_GENERATION"),10,64)
 if err!=nil{t.Fatal(err)}
 event:=os.Getenv("WINEBOT_TEST_EVENT")
 p:=scopeEmptyProof{g,"scope-a",true,true,true}
 _,err=lifecycleTransition(root,uint32(os.Geteuid()),g,event,"scope-a",p,func(s string){
  if s==stage{if err:=syscall.Kill(os.Getpid(),syscall.SIGKILL);err!=nil{panic(err)};select{}}
 })
 t.Fatalf("expected process death, err=%v",err)
}

func TestLifecycleCrashBoundaries(t *testing.T) {
 for _,event:=range []string{"reserve","launch_intent","quarantine","reconcile"}{
  for _,stage:=range []string{"before_rename","after_rename","after_sync"}{
   t.Run(event+"/"+stage,func(t *testing.T){
    root:=lifecycleTestRoot(t);uid:=uint32(os.Geteuid())
    if err:=lifecycleProvision(root,uid);err!=nil{t.Fatal(err)}
    g:=int64(0)
    if event!="reserve"{lifecycleMust(t,root,0,"reserve","scope-a",scopeEmptyProof{});g=1}
    if event=="quarantine" || event=="reconcile"{lifecycleMust(t,root,1,"launch_intent","scope-a",scopeEmptyProof{})}
    if event=="reconcile"{lifecycleMust(t,root,1,"quarantine","scope-a",scopeEmptyProof{})}
    old,err:=lifecycleRead(root,uid);if err!=nil{t.Fatal(err)}
    cmd:=exec.Command(os.Args[0],"-test.run=^TestLifecycleCrashChild$")
    cmd.Env=append(os.Environ(),"WINEBOT_TEST_CRASH_CHILD=1","WINEBOT_TEST_ROOT="+root,
     "WINEBOT_TEST_STAGE="+stage,"WINEBOT_TEST_EVENT="+event,"WINEBOT_TEST_GENERATION="+strconv.FormatInt(g,10))
    err=cmd.Run()
    ee,ok:=err.(*exec.ExitError)
    if !ok || ee.Sys().(syscall.WaitStatus).Signal()!=syscall.SIGKILL{t.Fatalf("not SIGKILL: %v",err)}
    s,err:=lifecycleRead(root,uid);if err!=nil{t.Fatal(err)}
    if stage=="before_rename"{if s!=old{t.Fatal("pre-rename state changed")}}else{
     want:=map[string]string{"reserve":"RESERVED","launch_intent":"RUNNING","quarantine":"QUARANTINED","reconcile":"IDLE"}[event]
     if s.Phase!=want || s.Generation!=1{t.Fatal(s)}
    }
    // A surviving non-idle generation cannot admit another writer.
    if s.Phase!="IDLE"{
     if _,err:=lifecycleTransition(root,uid,s.Generation,"reserve","scope-b",scopeEmptyProof{},nil);err==nil{t.Fatal("overlapping reserve")}
    }
   })
  }
 }
}
