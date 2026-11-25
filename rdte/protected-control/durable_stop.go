//go:build linux

package main

import (
 "bytes"
 "encoding/json"
 "errors"
 "io"
 "os"
 "path/filepath"
 "syscall"
)

const durableStopName = ".winebot-stop-v1.json"
const durableStopLock = ".winebot-stop-v1.lock"

// Lock ordering: ordinary journal lock -> STOP lock. STOP requests acquire
// ONLY the latter. Neither lock may be inherited by a guest. The STOP lock
// is never held over a dispatch callback or recursive scope observation.
func acquireStop(root string,uid uint32)(*os.File,*os.File,error){
 d,err:=validateRoot(root,uid)
 if err!=nil{return nil,nil,err}
 l,err:=ownedRegular(filepath.Join(root,durableStopLock),syscall.O_RDWR,uid,true)
 if err!=nil{d.Close();return nil,nil,err}
 if err=syscall.Flock(int(l.Fd()),syscall.LOCK_EX|syscall.LOCK_NB);err!=nil{
  l.Close();d.Close();return nil,nil,err
 }
 return d,l,nil
}

func readDurableStop(root string,uid uint32)(*lifecycleRecord,error){
 f,err:=ownedRegular(filepath.Join(root,durableStopName),syscall.O_RDONLY,uid,false)
 if errors.Is(err,os.ErrNotExist){return nil,nil}
 if err!=nil{return nil,err}
 defer f.Close()
 b,err:=io.ReadAll(io.LimitReader(f,maxRecordBytes+1))
 if err!=nil || len(b)>maxRecordBytes{return nil,errors.New("STOP record unreadable")}
 var s lifecycleRecord
 if err=json.Unmarshal(b,&s);err!=nil{return nil,err}
 canonical,err:=lifecycleBytes(s)
 if err!=nil || s.Phase!="QUARANTINED" || !bytes.Equal(b,canonical){
  return nil,errors.New("invalid STOP record")
 }
 return &s,nil
}

func requireNoDurableStop(root string,uid uint32)error{
 s,err:=readDurableStop(root,uid)
 if err!=nil{return err}
 if s!=nil{return errors.New("durable STOP latched")}
 return nil
}

// Sticky until a future independently qualified recovery authority exists.
// Missing marker means no recorded STOP only on a trusted nonrollback
// control volume; deletion/rollback by a trusted administrator is outside
// this reference's threat model. Never clear or replace a different STOP.
func requestDurableStop(root string,uid uint32,generation int64,scope string)error{
 d,l,err:=acquireStop(root,uid)
 if err!=nil{return err}
 defer d.Close();defer l.Close()
 s,err:=lifecycleRead(root,uid)
 if err!=nil{return err}
 if s.Phase=="IDLE" || s.Generation!=generation || s.Scope!=scope{
  return errors.New("stale STOP target")
 }
 prior,err:=readDurableStop(root,uid)
 if err!=nil{return err}
 if prior!=nil{
  if prior.Generation!=generation || prior.Scope!=scope{return errors.New("different STOP already latched")}
  return d.Sync()
 }
 s.Phase="QUARANTINED"
 b,err:=lifecycleBytes(s)
 if err!=nil{return err}
 f,err:=os.CreateTemp(root,".winebot-stop-write-")
 if err!=nil{return err}
 defer os.Remove(f.Name());defer f.Close()
 if _,err=f.Write(b);err!=nil{return err}
 if err=f.Sync();err!=nil{return err}
 if err=f.Close();err!=nil{return err}
 if err=os.Rename(f.Name(),filepath.Join(root,durableStopName));err!=nil{return err}
 return d.Sync()
}

// Cancellation acknowledgement and durable receipt remain distinct.
// If persistence fails, the local latch still closes; caller must report
// UNKNOWN rather than a durable STOP receipt. No actual kill implied.
func(e *emergencyDispatch) requestPersistentStop() (emergencyStatus,error){
 s:=e.requestStop()
 return s,requestDurableStop(e.gate.root,e.gate.uid,e.gate.generation,e.gate.scope)
}
