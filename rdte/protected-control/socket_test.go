//go:build linux

package main

import (
 "errors"
 "io"
 "net"
 "os"
 "path/filepath"
 "strings"
 "testing"
 "time"
)

func callControl(t *testing.T,l *net.UnixListener,root,msg string,ownerUID,trustedUID,trustedGID uint32)string{
 t.Helper()
 done:=make(chan error,1)
 go func(){
  conn,err:=l.AcceptUnix()
  if err==nil{handleControlConn(conn,root,ownerUID,trustedUID,trustedGID)}
  done<-err
 }()
 c,err:=net.DialUnix("unix",nil,&net.UnixAddr{Name:filepath.Join(root,socketName),Net:"unix"})
 if err!=nil{t.Fatal(err)}
 _=c.SetDeadline(time.Now().Add(3*time.Second))
 if _,err=c.Write([]byte(msg));err!=nil{t.Fatal(err)}
 if err=c.CloseWrite();err!=nil{t.Fatal(err)}
 r,err:=io.ReadAll(io.LimitReader(c,256))
 if err!=nil{t.Fatal(err)}
 c.Close()
 select{case err:=<-done:if err!=nil{t.Fatal(err)};case <-time.After(4*time.Second):t.Fatal("server stalled")}
 return string(r)
}

func TestActualPeerSocketCASAndReplay(t *testing.T){
 root,uid:=fixture(t)
 l,err:=listenControl(root,uid)
 if err!=nil{t.Fatal(err)}
 defer l.Close()
 gid:=uint32(os.Getegid())
 if x:=callControl(t,l,root,"{\"op\":\"read\"}",uid,uid,gid);x!="CONTROL_IPC=EMPTY\n"{t.Fatal(x)}
 m:="{\"op\":\"claim\",\"session_id\":\"synthetic\",\"expected_generation\":0,\"operation_id\":\"op-a\"}"
 for i:=0;i<2;i++{
  if x:=callControl(t,l,root,m,uid,uid,gid);x!="CONTROL_IPC=COMMITTED\n"{t.Fatal(x)}
 }
 if x:=callControl(t,l,root,"{\"op\":\"read\"}",uid,uid,gid);x!="CONTROL_IPC=EXISTS\n"{t.Fatal(x)}
 stale:="{\"op\":\"claim\",\"session_id\":\"other\",\"expected_generation\":0,\"operation_id\":\"op-b\"}"
 if x:=callControl(t,l,root,stale,uid,uid,gid);x!="CONTROL_IPC=REJECTED\n"{t.Fatal(x)}
 owner,err:=view(root,uid)
 if err!=nil||owner==nil||owner.Generation!=1{t.Fatalf("owner changed: %v",err)}
}

func TestActualPeerCredentialsFailClosed(t *testing.T){
 root,uid:=fixture(t)
 l,err:=listenControl(root,uid)
 if err!=nil{t.Fatal(err)}
 defer l.Close()
 gid:=uint32(os.Getegid())
 m:="{\"op\":\"claim\",\"session_id\":\"synthetic\",\"expected_generation\":0,\"operation_id\":\"op-a\"}"
 if x:=callControl(t,l,root,m,uid,uid+1,gid);x!="CONTROL_IPC=DENIED\n"{t.Fatal(x)}
 if x:=callControl(t,l,root,m,uid,uid,gid+1);x!="CONTROL_IPC=DENIED\n"{t.Fatal(x)}
 if _,err:=os.Stat(filepath.Join(root,ownerName));!errors.Is(err,os.ErrNotExist){t.Fatal("denied peer mutated owner")}
}

func TestStrictControlProtocolNegative(t *testing.T){
 root,uid:=fixture(t)
 l,err:=listenControl(root,uid)
 if err!=nil{t.Fatal(err)}
 defer l.Close()
 for _,bad:=range []string{
  "", "{}", "{\"op\":\"read\",\"op\":\"read\"}",
  "{\"op\":\"read\",\"session_id\":\"unexpected\"}", "{\"op\":\"stop\"}",
  "{\"op\":\"claim\",\"session_id\":\"s\",\"expected_generation\":0,\"operation_id\":\"o\",\"extra\":1}",
  "{\"op\":\"claim\",\"session_id\":\"s\",\"expected_generation\":0.1,\"operation_id\":\"o\"}",
  "{\"op\":\"claim\",\"session_id\":\"s\",\"expected_generation\":0,\"operation_id\":\"o\"} {}",
  strings.Repeat("X",maxRequest+1),
 }{
  if x:=callControl(t,l,root,bad,uid,uid,uint32(os.Getegid()));x!="CONTROL_IPC=MALFORMED\n"{t.Fatalf("invalid accepted: %q",x)}
 }
 if _,err:=os.Stat(filepath.Join(root,ownerName));!errors.Is(err,os.ErrNotExist){t.Fatal("malformed data modified owner")}
}

func TestStaleAndSymlinkSocketFailClosed(t *testing.T){
 root,uid:=fixture(t)
 l,err:=listenControl(root,uid)
 if err!=nil{t.Fatal(err)}
 p:=filepath.Join(root,socketName)
 st,err:=os.Lstat(p)
 if err!=nil||st.Mode().Perm()!=0600||st.Mode()&os.ModeSocket==0{t.Fatal("socket identity invalid")}
 if _,err=listenControl(root,uid);err==nil{t.Fatal("second listener started")}
 l.Close()
 if _,err=listenControl(root,uid);err==nil{t.Fatal("stale socket silently replaced")}
 if err=os.Remove(p);err!=nil{t.Fatal(err)}
 if err=os.Symlink("synthetic-destination",p);err!=nil{t.Fatal(err)}
 if _,err=listenControl(root,uid);err==nil{t.Fatal("symlink socket silently replaced")}
}
