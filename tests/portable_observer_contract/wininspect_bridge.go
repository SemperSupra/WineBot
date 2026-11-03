// SPDX-License-Identifier: MIT
// Test-only WinInspect-compatible read-only bridge. No private WinInspect RPC implementation.
package observercontract

import "errors"

var ErrReinspectionRequired = errors.New("reinspection_required")

// ReinspectionError retains only a fixed, non-identifying terminal cause.
// It does not contain a stream cursor, reader identity, target, or authority.
type ReinspectionError struct {
 Reason string
}
func (e *ReinspectionError) Error() string { return ErrReinspectionRequired.Error() }
func (e *ReinspectionError) Is(target error) bool { return target == ErrReinspectionRequired }

// InspectionHint intentionally contains no HWND, PID, title, control text,
// selector, target_ref, action token, or falsely resumable reader-name cursor.
// There is intentionally no public resume cursor in hint.v0. Legacy events.poll is unchanged.
type InspectionHint struct {
 Contract string `json:"contract"`
 Stream string `json:"stream"`
 Sequence int `json:"sequence"`
 Scope string `json:"scope"`
 Reason string `json:"reason"`
}

// ReadOnlyBridge translates bounded observations into conservative broad
// reinspection hints. Target-specific routing is forbidden until a trusted
// resolver has proved session/target epochs under the owner security gate.
type ReadOnlyBridge struct { ring *Fanout; consumer string }
func NewReadOnlyBridge(ring *Fanout,consumer string) (*ReadOnlyBridge,error) {
 if ring==nil || consumer=="" {return nil,ErrInvalid}
 if err:=ring.Subscribe(consumer);err!=nil{return nil,err}
 return &ReadOnlyBridge{ring:ring,consumer:consumer},nil
}
func (b *ReadOnlyBridge) Poll(max int) ([]InspectionHint,error) {
 frames,err:=b.ring.Poll(b.consumer,max)
 if err!=nil {
  if errors.Is(err,ErrCursorGap) {return nil,&ReinspectionError{Reason:"gap"}}
  return nil,err
 }
 out:=make([]InspectionHint,0,len(frames))
 for _,f:=range frames {
  reason:=f.Kind
  if f.Status!="observed" {reason=f.Status}
  out=append(out,InspectionHint{Contract:"wininspect.observer.hint.v0",Stream:f.Stream,Sequence:f.Sequence,Scope:"desktop",Reason:reason})
 }
 return out,nil
}
func (b *ReadOnlyBridge) Close() {b.ring.Unsubscribe(b.consumer)}
