//go:build linux

package main

import (
 "errors"
 "os"
 "path/filepath"
 "strings"
 "syscall"
 "testing"
)

func fixture(t *testing.T)(string,uint32){
 t.Helper()
 root:=t.TempDir()
 if err:=os.Chmod(root,0700);err!=nil {t.Fatal(err)}
 return root,uint32(os.Geteuid())
}

func TestClaimReplayAndStaleGeneration(t *testing.T) {
 root,uid:=fixture(t)
 first,err:=claim(root,uid,"session-a",0,"operation-a")
 if err!=nil || first.Generation!=1 {t.Fatalf("first: %v %+v",err,first)}
 again,err:=claim(root,uid,"session-a",0,"operation-a")
 if err!=nil || again!=first {t.Fatalf("idempotent: %v %+v",err,again)}
 if _,err=claim(root,uid,"session-b",0,"operation-b");err==nil {t.Fatal("stale generation accepted")}
 if _,err=claim(root,uid,"session-b",1,"operation-a");err==nil {t.Fatal("operation id reused")}
 second,err:=claim(root,uid,"session-b",1,"operation-b")
 if err!=nil || second.Generation!=2 {t.Fatalf("next: %v %+v",err,second)}
 read,err:=view(root,uid)
 if err!=nil || read==nil || *read!=second {t.Fatalf("persistent replay: %v %+v",err,read)}
}

func TestInputValidationAndPathCustody(t *testing.T){
 root,uid:=fixture(t)
 for _,bad:=range []string{"","../escape","session/escape","space here",strings.Repeat("a",129)}{
  if _,err:=claim(root,uid,bad,0,"good");err==nil {t.Fatalf("invalid id accepted: %q",bad)}
 }
 if _,err:=claim(root,uid,"good",0,"bad/operation");err==nil {t.Fatal("invalid operation")}
 if _,err:=claim(root,uid,"good",-1,"ok");err==nil {t.Fatal("negative generation")}
 if _,err:=claim(root,uid,"good",maxGeneration,"ok");err==nil {t.Fatal("overflow generation")}
 if _,err:=claim(root,uid+1,"good",0,"ok");err==nil {t.Fatal("alien UID accepted")}
 if err:=os.Chmod(root,0777);err!=nil {t.Fatal(err)}
 if _,err:=claim(root,uid,"good",0,"ok");err==nil {t.Fatal("guest-writable root accepted")}
}

func TestStrictRecordParser(t *testing.T){
 good:=`{"schema":"winebot/control-owner/v1","generation":1,"session_id":"session-a","operation_id":"op-1"}`
 r,err:=strictParse([]byte(good))
 if err!=nil || r.Generation!=1 {t.Fatalf("good rejected: %v",err)}
 for _,bad:=range []string{
  `{}`,
  `{"schema":"winebot/control-owner/v0","generation":1,"session_id":"a","operation_id":"b"}`,
  `{"schema":"winebot/control-owner/v1","generation":true,"session_id":"a","operation_id":"b"}`,
  `{"schema":"winebot/control-owner/v1","generation":1,"session_id":"a","operation_id":"b","extra":0}`,
  `{"schema":"winebot/control-owner/v1","schema":"winebot/control-owner/v1","generation":1,"session_id":"a","operation_id":"b"}`,
  good+` {}`,
  `{"schema":"winebot/control-owner/v1","generation":0,"session_id":"a","operation_id":"b"}`,
  `{"schema":"winebot/control-owner/v1","generation":1,"session_id":"../a","operation_id":"b"}`,
  strings.Repeat("x",maxRecordBytes+1),
 }{
  if _,err:=strictParse([]byte(bad));err==nil {t.Fatalf("bad record admitted: %q",bad[:min(len(bad),150)])}
 }
}

func TestSymlinkOwnerAndLockRefusal(t *testing.T){
 root,uid:=fixture(t)
 target:=filepath.Join(root,"untrusted")
 if err:=os.WriteFile(target,[]byte("unsafe"),0600);err!=nil {t.Fatal(err)}
 for _,name:=range []string{ownerName,lockName}{
  link:=filepath.Join(root,name)
  if err:=os.Symlink(target,link);err!=nil {t.Fatal(err)}
  if _,err:=claim(root,uid,"session",0,"operation");err==nil {t.Fatalf("%s symlink accepted",name)}
  if err:=os.Remove(link);err!=nil {t.Fatal(err)}
 }
}

func TestLockContentionAndNoCommit(t *testing.T){
 root,uid:=fixture(t)
 dir,lock,err:=acquire(root,uid)
 if err!=nil {t.Fatal(err)}
 defer dir.Close()
 defer lock.Close()
 _,err=claim(root,uid,"session-a",0,"op-a")
 if err==nil {t.Fatal("second OFD acquired exclusive lock")}
 if _,err=os.Stat(filepath.Join(root,ownerName));!errors.Is(err,os.ErrNotExist) {
  t.Fatalf("unauthorized commit file: %v",err)
 }
}

func TestCorruptionRefusesClaim(t *testing.T){
 root,uid:=fixture(t)
 path:=filepath.Join(root,ownerName)
 if err:=os.WriteFile(path,[]byte(`{"schema":"winebot/control-owner/v1","schema":"winebot/control-owner/v1","generation":1,"session_id":"a","operation_id":"b"}`),0600);err!=nil {t.Fatal(err)}
 if _,err:=claim(root,uid,"session-b",1,"op-b");err==nil {t.Fatal("duplicate key owner accepted")}
 if err:=os.Remove(path);err!=nil {t.Fatal(err)}
 if _,err:=claim(root,uid,"session-a",0,"op-a");err!=nil {t.Fatal(err)}
 fd,err:=syscall.Open(path,syscall.O_RDONLY|syscall.O_NOFOLLOW,0)
 if err!=nil {t.Fatal(err)}
 syscall.Close(fd)
}
