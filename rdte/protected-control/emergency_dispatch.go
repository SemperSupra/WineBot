//go:build linux

package main

import (
 "context"
 "errors"
 "sync"
 "time"
)

// emergencyDispatch is a reference for the sole trusted launch authority.
// STOP requests are independent of the writer journal lock and callback.
// The latch is process-local, not a durable STOP receipt. No method here
// grants reconciliation or replacement-writer permission.
type emergencyDispatch struct {
 mu sync.Mutex
 gate *writerGate
 ctx context.Context
 cancel context.CancelFunc
 requested bool
 submitted bool
 inFlight bool
 returned bool
 ambiguous bool
}

type emergencyStatus struct {
 StopRequested bool
 Submitted bool
 InFlight bool
 Returned bool
 Ambiguous bool
}

func newEmergencyDispatch(g *writerGate)(*emergencyDispatch,error){
 if g==nil{return nil,errors.New("missing writer gate")}
 ctx,cancel:=context.WithCancel(context.Background())
 return &emergencyDispatch{gate:g,ctx:ctx,cancel:cancel},nil
}

func(e *emergencyDispatch) statusLocked() emergencyStatus{
 return emergencyStatus{e.requested,e.submitted,e.inFlight,e.returned,e.ambiguous}
}

func(e *emergencyDispatch) status() emergencyStatus{
 e.mu.Lock();defer e.mu.Unlock()
 return e.statusLocked()
}

// A receipt acknowledges ONLY the in-memory request, not durable quarantine,
// worker termination, scope emptiness, or cancellation of an external effect.
func(e *emergencyDispatch) requestStop() emergencyStatus{
 e.mu.Lock()
 e.requested=true
 snapshot:=e.statusLocked()
 e.mu.Unlock()
 // No journal, scope or dispatch lock is acquired.
 e.cancel()
 return snapshot
}

// A separate trusted requester may persist STOP without owning this
// process's context. Read the atomic protected record without taking the
// ordinary journal lock. Unreadable or foreign evidence closes local
// dispatch conservatively; this is NOT an acknowledgement of persistence.
// The caller still owns external effect termination and reconciliation.
func(e *emergencyDispatch) observeExternalStop()bool{
 s,err:=readDurableStop(e.gate.root,e.gate.uid)
 if err==nil && s==nil{return false}
 // A matching marker or invalid/foreign evidence both deny continuation.
 // No generation is released or rewritten by this reader.
 e.requestStop()
 return true
}

func(e *emergencyDispatch) watchExternalStop(stop <-chan struct{},done chan<- struct{}){
 defer close(done)
 ticker:=time.NewTicker(25*time.Millisecond)
 defer ticker.Stop()
 for{
  if e.observeExternalStop(){return}
  select{
  case <-stop:return
  case <-e.ctx.Done():return
  case <-ticker.C:
  }
 }
}

// Caller owns worker scheduling. At most one submission; STOP linearizes
// against reservation. A previously reserved operation can race with STOP,
// and must be regarded as in flight until independently reconciled.
func(e *emergencyDispatch) run(dispatch func(context.Context)error)(err error){
 if dispatch==nil{return errors.New("missing dispatch")}
 e.mu.Lock()
 if e.requested || e.submitted{
  e.mu.Unlock()
  return errors.New("dispatch admission closed")
 }
 e.submitted=true;e.inFlight=true
 e.mu.Unlock()
 completed:=false
 stopWatch:=make(chan struct{})
 watchDone:=make(chan struct{})
 go e.watchExternalStop(stopWatch,watchDone)
 defer func(){
  close(stopWatch)
  <-watchDone
  // Recheck at callback return, including when a local cancellation has
  // already stopped the watcher. A subsequent request still fences future
  // journal admission, but cannot retroactively cancel a completed effect.
  e.observeExternalStop()
  e.mu.Lock()
  e.inFlight=false;e.returned=true
  e.ambiguous=!completed || err!=nil || e.requested
  e.mu.Unlock()
  e.cancel()
 }()
 err=e.gate.launch(func()error{
  if err:=e.ctx.Err();err!=nil{return err}
  return dispatch(e.ctx)
 })
 completed=true
 return err
}
