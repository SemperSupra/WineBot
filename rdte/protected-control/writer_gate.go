//go:build linux

package main

import (
 "crypto/rand"
 "encoding/hex"
 "errors"
 "os"
 "sync"
)

// Offline reference only. A trusted caller exclusively controls admission,
// migration and dispatch into the admitted scope. No external queue is
// permitted. A lost handle cannot be reconstructed from a PID or pathname.
type writerGate struct {
 mu sync.Mutex
 root string
 uid uint32
 generation int64
 scope string
 observe func() (bool,error)
 scopeDir *os.File
 scopeID cgroupIdentity
 uncertain bool
 retired bool
}

func newWriterGate(root string,uid uint32,expected int64,dir *os.File,id cgroupIdentity)(*writerGate,error){
 // The caller retains a fresh, protected scope descriptor throughout this
 // handle's lifetime. The caller must not close or reuse it concurrently.
 if dir==nil{return nil,errors.New("missing scope descriptor")}
 g,err:=reserveWriterGate(root,uid,expected,func()(bool,error){
  return cgroupPopulated(dir,id)
 })
 if err!=nil{return nil,err}
 g.scopeDir=dir
 g.scopeID=id
 return g,nil
}

// Internal observation seam for deterministic tests. Never exposed to IPC.
func reserveWriterGate(root string,uid uint32,expected int64,observe func()(bool,error))(*writerGate,error){
 if observe==nil{return nil,errors.New("missing scope observer")}
 d,l,err:=acquire(root,uid)
 if err!=nil{return nil,err}
 defer d.Close();defer l.Close()
 s,err:=lifecycleRead(root,uid)
 if err!=nil{return nil,err}
 if s.Phase!="IDLE" || s.Generation!=expected || expected>=maxGeneration{return nil,errors.New("reserve refused")}
 p,err:=observe()
 if err!=nil || p{return nil,errors.New("scope not empty")}
 var token [16]byte
 if _,err=rand.Read(token[:]);err!=nil{return nil,err}
 sd,sl,err:=acquireStop(root,uid)
 if err!=nil{return nil,err}
 defer sd.Close();defer sl.Close()
 if err=requireNoDurableStop(root,uid);err!=nil{return nil,err}
 s.Generation++;s.Scope=hex.EncodeToString(token[:]);s.Phase="RESERVED"
 if err=lifecycleWrite(root,d,s,nil);err!=nil{return nil,err}
 return &writerGate{root:root,uid:uid,generation:s.Generation,scope:s.Scope,observe:observe},nil
}

func(g *writerGate) bound(s lifecycleRecord)bool{
 return s.Generation==g.generation && s.Scope==g.scope && !g.retired
}

// dispatch MUST be synchronous and trusted, with no external pending launch
// on success. An error or panic leaves the generation ambiguous; no retry
// or automatic release through this handle is permitted.
func(g *writerGate) launch(dispatch func()error)error{
 g.mu.Lock();defer g.mu.Unlock()
 if dispatch==nil || g.uncertain || g.retired{return errors.New("launch refused")}
 d,l,err:=acquire(g.root,g.uid)
 if err!=nil{return err}
 defer d.Close();defer l.Close()
 s,err:=lifecycleRead(g.root,g.uid)
 if err!=nil{return err}
 if !g.bound(s) || s.Phase!="RESERVED"{return errors.New("launch refused")}
 // Serialize the durable intent against STOP; release before dispatch.
 sd,sl,err:=acquireStop(g.root,g.uid)
 if err!=nil{return err}
 err=func()error{
  defer sd.Close();defer sl.Close()
  if err:=requireNoDurableStop(g.root,g.uid);err!=nil{return err}
  s.Phase="RUNNING"
  return lifecycleWrite(g.root,d,s,nil)
 }()
 if err!=nil{g.uncertain=true;return err}
 g.uncertain=true
 if err=dispatch();err!=nil{return err}
 g.uncertain=false
 return nil
}

// STOP closes this reference's launch gate by durable phase transition.
// The caller may separately drain the admitted scope, never arbitrary PIDs.
// Unknown dispatch completion cannot be cleared just by observing emptiness.
func(g *writerGate) stopAndReconcile()error{
 g.mu.Lock();defer g.mu.Unlock()
 if g.retired{return errors.New("retired handle")}
 d,l,err:=acquire(g.root,g.uid)
 if err!=nil{return err}
 defer d.Close();defer l.Close()
 s,err:=lifecycleRead(g.root,g.uid)
 if err!=nil{return err}
 if !g.bound(s) || (s.Phase!="RESERVED" && s.Phase!="RUNNING" && s.Phase!="QUARANTINED"){
  return errors.New("stop refused")
 }
 s.Phase="QUARANTINED"
 if err=lifecycleWrite(g.root,d,s,nil);err!=nil{
  g.uncertain=true;return err
 }
 if g.uncertain{return errors.New("dispatch completion unknown")}
 p,err:=g.observe()
 if err!=nil || p{return errors.New("scope not proven empty")}
 // Observe before taking the independent STOP lock, then serialize the
 // final release against any STOP latched during observation.
 sd,sl,err:=acquireStop(g.root,g.uid)
 if err!=nil{return err}
 defer sd.Close();defer sl.Close()
 if err=requireNoDurableStop(g.root,g.uid);err!=nil{return err}
 s.Phase="IDLE";s.Scope=""
 if err=lifecycleWrite(g.root,d,s,nil);err!=nil{
  g.retired=true;return err
 }
 g.retired=true
 return nil
}
