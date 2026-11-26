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
const deploymentModeName = ".winebot-deployment-gate.lock"
const trustedDeploymentMode = "winebot-trusted-lifecycle-v1\n"

type lifecycleRecord struct {
 Schema string `json:"schema"`
 Generation int64 `json:"generation"`
 Phase string `json:"phase"`
 Scope string `json:"scope"`
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

// Publish the trusted-mode sentinel atomically at the existing legacy gate
// lock pathname. A legacy gate that wins creation, even if no longer live,
// prevents automatic migration. The marker is intentionally never removed
// on error: an incomplete provision requires independent reconciliation.
// Assumes updated cooperating legacy gate and protected nonrollback root.
func claimTrustedDeploymentMode(root string,dir *os.File)error{
 f,err:=os.CreateTemp(root,".winebot-mode-write-")
 if err!=nil{return err}
 defer f.Close()
 defer os.Remove(f.Name())
 if _,err=f.WriteString(trustedDeploymentMode);err!=nil{return err}
 if err=f.Sync();err!=nil{return err}
 if err=f.Close();err!=nil{return err}
 // Link is atomic and refuses an existing name, unlike Rename.
 if err=os.Link(f.Name(),filepath.Join(root,deploymentModeName));err!=nil{return errors.New("deployment authority already selected or unavailable")}
 if err=os.Remove(f.Name());err!=nil{return err}
 return dir.Sync()
}

// Explicit initial provisioning only on an independently admitted NEW volume.
// Runtime reads/transitions NEVER recreate a missing or corrupt journal.
func lifecycleProvision(root string,uid uint32) error {
 dir,lock,err:=acquire(root,uid)
 if err!=nil{return err}
 defer dir.Close();defer lock.Close()
 sd,sl,err:=acquireStop(root,uid)
 if err!=nil{return err}
 defer sd.Close();defer sl.Close()
 if err=requireNoDurableStop(root,uid);err!=nil{return err}
 if _,err=os.Lstat(filepath.Join(root,lifecycleName));!os.IsNotExist(err){
  return errors.New("provision refused")
 }
 if err=claimTrustedDeploymentMode(root,dir);err!=nil{return err}
 return lifecycleWrite(root,dir,lifecycleRecord{Schema:lifecycleSchema,Phase:"IDLE"},nil)
}

