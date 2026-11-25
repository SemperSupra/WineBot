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

const lifecycleName = ".winebot-lifecycle-v1.json"
const lifecycleSchema = "winebot/writer-lifecycle/v1"

type lifecycleRecord struct {
 Schema string `json:"schema"`
 Generation int64 `json:"generation"`
 Phase string `json:"phase"`
 Scope string `json:"scope"`
}

// This is a typed input to a TRUSTED caller, not authenticated evidence.
// Never expose this structure as a guest request or infer it from guest PID.
type scopeEmptyProof struct {
 Generation int64
 Scope string
 GateClosed, NoPending, NoLive bool
}

func lifecycleValid(s lifecycleRecord) bool {
 if s.Schema != lifecycleSchema || s.Generation < 0 { return false }
 switch s.Phase {
 case "IDLE": return s.Scope == ""
 case "RESERVED", "RUNNING", "QUARANTINED":
  return s.Generation > 0 && identifier.MatchString(s.Scope)
 default: return false
 }
}

func lifecycleBytes(s lifecycleRecord) ([]byte,error) {
 if !lifecycleValid(s) { return nil,errors.New("invalid lifecycle record") }
 b,err:=json.Marshal(s)
 return append(b,'\n'),err
}

func lifecycleRead(root string,uid uint32) (lifecycleRecord,error) {
 var s lifecycleRecord
 f,err:=ownedRegular(filepath.Join(root,lifecycleName),syscall.O_RDONLY,uid,false)
 if err!=nil {return s,err}
 defer f.Close()
 b,err:=io.ReadAll(io.LimitReader(f,maxRecordBytes+1))
 if err!=nil || len(b)>maxRecordBytes {return s,errors.New("journal unreadable")}
 if err=json.Unmarshal(b,&s);err!=nil{return s,err}
 canonical,err:=lifecycleBytes(s)
 if err!=nil || !bytes.Equal(b,canonical) {return s,errors.New("noncanonical lifecycle record")}
 return s,nil
}

// fault is an internal test hook only. A failed or ambiguous commit grants
// no effect permission. Recovery must read the record and quarantine.
func lifecycleWrite(root string,dir *os.File,s lifecycleRecord,fault func(string)) error {
 b,err:=lifecycleBytes(s)
 if err!=nil{return err}
 f,err:=os.CreateTemp(root,".winebot-lifecycle-write-")
 if err!=nil{return err}
 defer os.Remove(f.Name())
 defer f.Close()
 if _,err=f.Write(b);err!=nil{return err}
 if err=f.Sync();err!=nil{return err}
 if err=f.Close();err!=nil{return err}
 if fault!=nil{fault("before_rename")}
 if err=os.Rename(f.Name(),filepath.Join(root,lifecycleName));err!=nil{return err}
 if fault!=nil{fault("after_rename")}
 if err=dir.Sync();err!=nil{return err}
 if fault!=nil{fault("after_sync")}
 return nil
}

// Explicit initial provisioning only on an independently admitted NEW volume.
// Runtime reads/transitions NEVER recreate a missing or corrupt journal.
func lifecycleProvision(root string,uid uint32) error {
 dir,lock,err:=acquire(root,uid)
 if err!=nil{return err}
 defer dir.Close();defer lock.Close()
 if _,err=os.Lstat(filepath.Join(root,lifecycleName));!os.IsNotExist(err){
  return errors.New("provision refused")
 }
 return lifecycleWrite(root,dir,lifecycleRecord{Schema:lifecycleSchema,Phase:"IDLE"},nil)
}

// The trusted actuator must close the actual launch gate BEFORE recording
// quarantine, and prove it stayed closed until reconciliation. The journal
// itself does not launch, cancel, observe or kill any real execution scope.
func lifecycleTransition(root string,uid uint32,expected int64,event,scope string,proof scopeEmptyProof,fault func(string)) (lifecycleRecord,error) {
 var zero lifecycleRecord
 dir,lock,err:=acquire(root,uid)
 if err!=nil{return zero,err}
 defer dir.Close();defer lock.Close()
 s,err:=lifecycleRead(root,uid)
 if err!=nil{return zero,err}
 if s.Generation!=expected{return zero,errors.New("stale generation")}
 // Re-establish directory durability after an ambiguous preceding rename.
 if err=dir.Sync();err!=nil{return zero,err}
 switch event {
 case "reserve":
  if s.Phase!="IDLE" || expected>=maxGeneration || !identifier.MatchString(scope){return zero,errors.New("reserve refused")}
  s.Generation++;s.Scope=scope;s.Phase="RESERVED"
 case "launch_intent":
  if s.Phase!="RESERVED" || scope!=s.Scope{return zero,errors.New("launch refused")}
  s.Phase="RUNNING"
 case "quarantine":
  if (s.Phase!="RESERVED" && s.Phase!="RUNNING" && s.Phase!="QUARANTINED") || scope!=s.Scope{return zero,errors.New("quarantine refused")}
  s.Phase="QUARANTINED"
 case "reconcile":
  if s.Phase!="QUARANTINED" || scope!=s.Scope || proof.Generation!=s.Generation ||
   proof.Scope!=s.Scope || !proof.GateClosed || !proof.NoPending || !proof.NoLive{return zero,errors.New("reconcile refused")}
  s.Phase="IDLE";s.Scope=""
 default:return zero,errors.New("unknown lifecycle transition")
 }
 if err=lifecycleWrite(root,dir,s,fault);err!=nil{return zero,err}
 return s,nil
}
