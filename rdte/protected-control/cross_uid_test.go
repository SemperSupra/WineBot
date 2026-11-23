//go:build linux

package main

import (
 "errors"
 "io"
 "net"
 "os"
 "os/exec"
 "path/filepath"
 "syscall"
 "testing"
 "time"
)

// Executed only from a separate numeric-UID guest child in the isolated
// disposable Docker test. Never reads a WineBot production mount.
func TestSyntheticGuestSocketClient(t *testing.T){
 if os.Getenv("WINEBOT_SYNTHETIC_GUEST")!="1"{return}
 if os.Geteuid()!=1000||os.Getegid()!=1000{t.Fatal("guest identity invalid")}
 path:=os.Getenv("WINEBOT_SYNTHETIC_SOCKET")
 if !filepath.IsAbs(path){t.Fatal("socket fixture invalid")}
 c,err:=net.DialTimeout("unix",path,2*time.Second)
 if err!=nil{t.Fatal("guest could not reach deliberately exposed fixture")}
 defer c.Close()
 _=c.SetDeadline(time.Now().Add(2*time.Second))
 _,err=c.Write([]byte("{\"op\":\"claim\",\"session_id\":\"guest\",\"expected_generation\":0,\"operation_id\":\"forged\"}"))
 if err!=nil{t.Fatal("guest send failed")}
 conn,ok:=c.(*net.UnixConn)
 if !ok{t.Fatal("guest transport invalid")}
 if err=conn.CloseWrite();err!=nil{t.Fatal("guest half-close failed")}
 reply,err:=io.ReadAll(io.LimitReader(c,256))
 if err!=nil{t.Fatal("guest denial unreadable")}
 if string(reply)!="CONTROL_IPC=DENIED\n"{t.Fatal("kernel rejected credential proof absent")}
}

// Requires only a root process INSIDE a private OCI container permitted
// CAP_SETUID/GID; tests run against fresh synthetic /tmp state.
func TestRealCrossUIDGuestDeniedEvenWhenSocketDACPermissive(t *testing.T){
 if os.Geteuid()!=0{t.Skip("Docker-only root test")}
 root,err:=os.MkdirTemp("/tmp","winebot-synthetic-peer-")
 if err!=nil{t.Fatal("fixture create failed")}
 defer os.RemoveAll(root)
 if err=os.Chmod(root,0700);err!=nil{t.Fatal("fixture permissions failed")}
 listener,err:=listenControl(root,0)
 if err!=nil{t.Fatal("root control listener unavailable")}
 defer listener.Close()
 // Deliberately weaken DAC ONLY inside this synthetic tempdir. A guest
 // must actually connect, then be rejected by kernel SO_PEERCRED, proving
 // broker authorization is independent of filesystem access.
 socket:=filepath.Join(root,socketName)
 if err=os.Chmod(root,0755);err!=nil{t.Fatal("fixture expose failed")}
 if err=os.Chmod(socket,0666);err!=nil{t.Fatal("socket fixture expose failed")}
 complete:=make(chan error,1)
 go func(){
  c,err:=listener.AcceptUnix()
  if err==nil{handleControlConn(c,root,0,0,0)}
  complete<-err
 }()
 child:=exec.Command(os.Args[0],"-test.run=^TestSyntheticGuestSocketClient$")
 child.Env=append(os.Environ(),
  "WINEBOT_SYNTHETIC_GUEST=1",
  "WINEBOT_SYNTHETIC_SOCKET="+socket,
 )
 child.SysProcAttr=&syscall.SysProcAttr{
  Credential:&syscall.Credential{Uid:1000,Gid:1000},
 }
 output,err:=child.CombinedOutput()
 _=output // No guest-controlled output or synthetic socket path published.
 if err!=nil{t.Fatal("separate guest process failed negative probe")}
 select{
 case err:=<-complete:
  if err!=nil{t.Fatal("control accept failed")}
 case <-time.After(4*time.Second):
  t.Fatal("control broker stalled on guest identity")
 }
 if _,err:=os.Lstat(filepath.Join(root,ownerName));!errors.Is(err,os.ErrNotExist){
  t.Fatal("unauthorized guest modified owner state")
 }
 if err=os.Chmod(socket,0600);err!=nil{t.Fatal("socket fixture restoration failed")}
 if err=os.Chmod(root,0700);err!=nil{t.Fatal("directory fixture restoration failed")}
}
