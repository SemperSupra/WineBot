//go:build linux

package main

import (
 "context"
 "errors"
 "sync"
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
 defer func(){
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
