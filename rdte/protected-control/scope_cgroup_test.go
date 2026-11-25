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

func TestCgroupEventStrictness(t *testing.T){
 for _,tc:=range []struct{input string;pop,valid bool}{
  {"populated 0\nfrozen 0\n",false,true},
  {"populated 1\nfrozen 0\n",true,true},
  {"populated 1\n",true,true},
  {"",false,false},{"populated 2\n",false,false},
  {"populated 0\npopulated 1\n",false,false},
  {"frozen 0\n",false,false},{"populated 0",false,false},
  {"populated  0\n",false,false},{"populated 0\nunknown 0\n",false,false},
 }{
  p,err:=parseCgroupPopulated([]byte(tc.input))
  if (err==nil)!=tc.valid || (tc.valid && p!=tc.pop){t.Fatal("event parser mismatch")}
 }
 f,err:=os.Open(t.TempDir())
 if err!=nil{t.Fatal(err)}
 defer f.Close()
 if _,err=cgroupID(f);err==nil{t.Fatal("ordinary directory admitted")}
}

func TestCgroupRealNestedFixture(t *testing.T){
 if os.Getenv("WINEBOT_REAL_CGROUP_FIXTURE")!="1"{t.Skip("dedicated disposable runner only")}
 if os.Geteuid()!=0{t.Fatal("fixture requires root")}
 root,err:=os.MkdirTemp("/sys/fs/cgroup","winebot-r043-fixture-")
 if err!=nil{t.Fatal(err)}
 defer os.Remove(root)
 nested:=filepath.Join(root,"nested")
 if err=os.Mkdir(nested,0700);err!=nil{t.Fatal(err)}
 defer os.Remove(nested)
 fd,err:=syscall.Open(root,syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC,0)
 if err!=nil{t.Fatal(err)}
 dir:=os.NewFile(uintptr(fd),"synthetic scope")
 defer dir.Close()
 id,err:=cgroupID(dir)
 if err!=nil{t.Fatal(err)}
 bad:=id;bad.Inode^=1
 if _,err=cgroupPopulated(dir,bad);err==nil{t.Fatal("wrong identity admitted")}
 if p,err:=cgroupPopulated(dir,id);err!=nil || p{t.Fatal("fresh scope not empty",err)}
 child:=exec.Command("/bin/sleep","30")
 if err=child.Start();err!=nil{t.Fatal(err)}
 done:=make(chan error,1)
 go func(){done<-child.Wait()}()
 reaped:=false
 defer func(){
  if !reaped{
   _=child.Process.Kill()
   select{case <-done:case <-time.After(5*time.Second):t.Error("fixture cleanup timeout")}
  }
 }()
 if err=os.WriteFile(filepath.Join(nested,"cgroup.procs"),[]byte(strconv.Itoa(child.Process.Pid)),0600);err!=nil{t.Fatal(err)}
 direct,err:=os.ReadFile(filepath.Join(root,"cgroup.procs"))
 if err!=nil || len(direct)!=0{t.Fatal("parent scope should have no direct tasks",err)}
 if p,err:=cgroupPopulated(dir,id);err!=nil || !p{t.Fatal("nested live process not observed",err)}
 if err=killCgroupFixture(dir,bad);err==nil{t.Fatal("wrong scope kill accepted")}
 if err=killCgroupFixture(dir,id);err!=nil{t.Fatal(err)}
 select{
 case err=<-done:
  reaped=true
  ee,ok:=err.(*exec.ExitError)
  if !ok || ee.Sys().(syscall.WaitStatus).Signal()!=syscall.SIGKILL{t.Fatal("expected fixture SIGKILL",err)}
 case <-time.After(5*time.Second):t.Fatal("recursive kill timeout")
 }
 deadline:=time.Now().Add(5*time.Second)
 for{
  p,err:=cgroupPopulated(dir,id)
  if err!=nil{t.Fatal(err)}
  if !p{break}
  if time.Now().After(deadline){t.Fatal("scope not empty")}
  time.Sleep(10*time.Millisecond)
 }
 if err=os.Remove(nested);err!=nil{t.Fatal(err)}
 if err=os.Remove(root);err!=nil{t.Fatal(err)}
 if _,err=cgroupPopulated(dir,id);err==nil{t.Fatal("removed scope accepted")}
}
