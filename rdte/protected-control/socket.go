//go:build linux

package main

import (
 "bytes"
 "encoding/json"
 "errors"
 "io"
 "net"
 "os"
 "path/filepath"
 "syscall"
 "time"
)

const socketName=".winebot-control-v1.sock"
const maxRequest=2048

type controlRequest struct{
 Op string
 Session string
 Generation int64
 Operation string
}

func parseControlRequest(data []byte)(controlRequest,error){
 var zero controlRequest
 if len(data)==0||len(data)>maxRequest{return zero,errors.New("invalid request size")}
 dec:=json.NewDecoder(bytes.NewReader(data))
 token,err:=dec.Token()
 if err!=nil||token!=json.Delim('{'){return zero,errors.New("invalid object")}
 fields:=map[string]json.RawMessage{}
 for dec.More(){
  keyToken,err:=dec.Token()
  key,ok:=keyToken.(string)
  if err!=nil||!ok{return zero,errors.New("invalid key")}
  if _,found:=fields[key];found{return zero,errors.New("duplicate key")}
  switch key{case "op","session_id","expected_generation","operation_id":default:return zero,errors.New("unknown key")}
  var value json.RawMessage
  if err=dec.Decode(&value);err!=nil{return zero,errors.New("invalid value")}
  fields[key]=value
 }
 token,err=dec.Token()
 if err!=nil||token!=json.Delim('}'){return zero,errors.New("invalid object end")}
 if _,err=dec.Token();err!=io.EOF{return zero,errors.New("trailing data")}
 var req controlRequest
 if err=json.Unmarshal(fields["op"],&req.Op);err!=nil{return zero,errors.New("invalid operation type")}
 switch req.Op{
 case "read":
  if len(fields)!=1{return zero,errors.New("read has extra fields")}
 case "claim":
  if len(fields)!=4{return zero,errors.New("missing claim fields")}
  if err=json.Unmarshal(fields["session_id"],&req.Session);err!=nil{return zero,errors.New("invalid session type")}
  if err=json.Unmarshal(fields["operation_id"],&req.Operation);err!=nil{return zero,errors.New("invalid operation id type")}
  if err=json.Unmarshal(fields["expected_generation"],&req.Generation);err!=nil{return zero,errors.New("invalid generation type")}
  if !identifier.MatchString(req.Session)||!identifier.MatchString(req.Operation)||req.Generation<0||req.Generation>=maxGeneration{
   return zero,errors.New("invalid claim")}
 default:return zero,errors.New("unsupported action")
 }
 return req,nil
}

func controlPeer(c *net.UnixConn)(*syscall.Ucred,error){
 raw,err:=c.SyscallConn()
 if err!=nil{return nil,err}
 var cred *syscall.Ucred
 var socketErr error
 err=raw.Control(func(fd uintptr){
  cred,socketErr=syscall.GetsockoptUcred(int(fd),syscall.SOL_SOCKET,syscall.SO_PEERCRED)
 })
 if err!=nil{return nil,err}
 if socketErr!=nil{return nil,socketErr}
 if cred==nil||cred.Pid<=0{return nil,errors.New("invalid kernel peer")}
 return cred,nil
}

func handleControlConn(c *net.UnixConn,root string,ownerUID,trustedUID,trustedGID uint32){
 defer c.Close()
 _=c.SetDeadline(time.Now().Add(2*time.Second))
 cred,err:=controlPeer(c)
 if err!=nil||cred.Uid!=trustedUID||cred.Gid!=trustedGID{
  _,_=io.WriteString(c,"CONTROL_IPC=DENIED\n")
  return
 }
 data,err:=io.ReadAll(io.LimitReader(c,maxRequest+1))
 if err!=nil||len(data)>maxRequest{
  _,_=io.WriteString(c,"CONTROL_IPC=MALFORMED\n")
  return
 }
 request,err:=parseControlRequest(data)
 if err!=nil{
  _,_=io.WriteString(c,"CONTROL_IPC=MALFORMED\n")
  return
 }
 result:="CONTROL_IPC=REJECTED\n"
 if request.Op=="read"{
  r,err:=view(root,ownerUID)
  if err==nil{
   if r==nil{result="CONTROL_IPC=EMPTY\n"}else{result="CONTROL_IPC=EXISTS\n"}
  }
 }else if request.Op=="claim"{
  if _,err:=claim(root,ownerUID,request.Session,request.Generation,request.Operation);err==nil{
   result="CONTROL_IPC=COMMITTED\n"
  }
 }
 _,_=io.WriteString(c,result)
}

// Never auto-unlink a stale socket or replace an active endpoint.
func listenControl(root string,uid uint32)(*net.UnixListener,error){
 dir,err:=validateRoot(root,uid)
 if err!=nil{return nil,err}
 _=dir.Close()
 path:=filepath.Join(root,socketName)
 if _,err=os.Lstat(path);err==nil{return nil,errors.New("socket already exists")}
 if !errors.Is(err,os.ErrNotExist){return nil,errors.New("socket path unavailable")}
 l,err:=net.ListenUnix("unix",&net.UnixAddr{Name:path,Net:"unix"})
 if err!=nil{return nil,errors.New("listener unavailable")}
 l.SetUnlinkOnClose(false)
 if err=os.Chmod(path,0600);err!=nil{l.Close();return nil,errors.New("socket chmod failed")}
 st,err:=os.Lstat(path)
 if err!=nil||st.Mode()&os.ModeSocket==0||st.Mode().Perm()!=0600{
  l.Close();return nil,errors.New("socket identity rejected")
 }
 return l,nil
}

// Production CLI uses ownerUID=trustedUID=trustedGID=0. Unit tests use
// synthetic directories and the local process's actual kernel identity.
func serveControl(root string,ownerUID,trustedUID,trustedGID uint32)error{
 l,err:=listenControl(root,ownerUID)
 if err!=nil{return err}
 defer l.Close()
 for{
  c,err:=l.AcceptUnix()
  if err!=nil{return errors.New("accept failed")}
  handleControlConn(c,root,ownerUID,trustedUID,trustedGID)
 }
}
