//go:build linux

package main

import (
 "errors"
 "os"
 "sync"
 "syscall"
)

// scopeKeeper is a non-deployed reference for trusted custody independent
// of a disposable supervisor. It never grants permission to launch or retry.
// Loss of this held descriptor requires separate recovery authority.
type scopeKeeper struct {
 mu sync.Mutex
 root string
 uid uint32
 generation int64
 scope string
 id cgroupIdentity
 dir *os.File
}

// Bind retention to the admitted gate's descriptor, never a fresh scope
// selected by a caller. A supplied descriptor is only a consistency check.
// This is not a guest-facing API.
func retainScope(g *writerGate,dir *os.File,id cgroupIdentity)(*scopeKeeper,error){
 g.mu.Lock();defer g.mu.Unlock()
 d,l,err:=acquire(g.root,g.uid)
 if err!=nil{return nil,err}
 defer d.Close();defer l.Close()
 s,err:=lifecycleRead(g.root,g.uid)
 if err!=nil{return nil,err}
 if !g.bound(s) || s.Phase!="RESERVED"{return nil,errors.New("scope retention refused")}
 if dir==nil || g.scopeDir==nil || id!=g.scopeID{return nil,errors.New("scope binding rejected")}
 actual,err:=cgroupID(dir)
 if err!=nil || actual!=g.scopeID{return nil,errors.New("scope identity rejected")}
 actual,err=cgroupID(g.scopeDir)
 if err!=nil || actual!=g.scopeID{return nil,errors.New("admitted scope identity lost")}
 fd,_,errno:=syscall.Syscall(syscall.SYS_FCNTL,g.scopeDir.Fd(),uintptr(syscall.F_DUPFD_CLOEXEC),0)
 if errno!=0{return nil,errno}
 retained:=os.NewFile(fd,"trusted retained scope")
 actual,err=cgroupID(retained)
 if err!=nil || actual!=id{retained.Close();return nil,errors.New("scope duplication rejected")}
 return &scopeKeeper{root:g.root,uid:g.uid,generation:s.Generation,scope:s.Scope,id:id,dir:retained},nil
}

func(k *scopeKeeper) close(){
 k.mu.Lock();defer k.mu.Unlock()
 if k.dir!=nil{_ = k.dir.Close();k.dir=nil}
}

// Only invoke after independently confirming supervisor death and closing
// all launch/migration paths. The held lock serializes journal changes, but
// does NOT by itself establish either of these external preconditions.
// Even a valid empty observation leaves QUARANTINED: pending effects and
// ambiguous completion require a distinct reconciliation authority.
func(k *scopeKeeper) quarantineAndObserve()(bool,error){
 k.mu.Lock();defer k.mu.Unlock()
 if k.dir==nil{return false,errors.New("trusted custody lost")}
 d,l,err:=acquire(k.root,k.uid)
 if err!=nil{return false,err}
 defer d.Close();defer l.Close()
 s,err:=lifecycleRead(k.root,k.uid)
 if err!=nil{return false,err}
 if s.Generation!=k.generation || s.Scope!=k.scope ||
  (s.Phase!="RESERVED" && s.Phase!="RUNNING" && s.Phase!="QUARANTINED"){
  return false,errors.New("stale custody")
 }
 s.Phase="QUARANTINED"
 if err=lifecycleWrite(k.root,d,s,nil);err!=nil{return false,err}
 return cgroupPopulated(k.dir,k.id)
}
