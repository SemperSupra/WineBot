// SPDX-License-Identifier: MIT
// Test-only, read-only session scoped observer relay.
// No HWND/PID or target correlation. No actuation authority or live RPC.
package observercontract

import "errors"

var ErrRelayStale = errors.New("relay_requires_reinspection")

// ScopedRelay is single-writer only: a trusted supervisor owns lifetime and
// supplies a fresh, unique stream identifier on every source incarnation.
// It rejects mixed streams and sequence replay BEFORE exposing any hints.
type ScopedRelay struct {
    ring *Fanout
    stream string
    source string
    generation uint64
    started bool
    stale bool
    next int
}

func NewScopedRelay(stream, source string, generation uint64, capacity int) (*ScopedRelay, error) {
    if stream == "" || source == "" || len(stream)>96 || len(source)>96 || generation==0 {
        return nil, ErrInvalid
    }
    ring,err:=NewFanout(capacity)
    if err!=nil{return nil,err}
    return &ScopedRelay{ring:ring,stream:stream,source:source,generation:generation,next:0},nil
}

func isSupportedObservation(kind string) bool {
    for _,value:=range canonical {
        if value==kind {return true}
    }
    return false
}

// Accept consumes normalized, validated adapter Frames only. Calling Accept is
// never an attestation that an actual window or desktop identity was resolved.
func (r *ScopedRelay) Accept(f Frame) error {
    if r==nil || r.stale {return ErrRelayStale}
    if f.Contract!=Contract || f.Stream!=r.stream || f.Source!=r.source {
        r.stale=true
        return ErrRelayStale
    }
    if !r.started {
        if f.Status!="ready" || f.Sequence!=0 || f.Kind!="" {
            r.stale=true
            return ErrRelayStale
        }
        if err:=r.ring.Publish(f);err!=nil {r.stale=true;return ErrRelayStale}
        r.started=true
        r.next=1
        return nil
    }
    if f.Status=="observed" && f.Sequence==r.next &&
       f.Sequence>=1 && f.Sequence<=128 && isSupportedObservation(f.Kind) {
        if err:=r.ring.Publish(f);err!=nil {r.stale=true;return ErrRelayStale}
        r.next++
        return nil
    }
    // Overflow, unsupported, sequence gaps, replays, unexpected readiness and
    // forged event statuses demand a new snapshot and fresh incarnation.
    r.stale=true
    return ErrRelayStale
}

type ScopedBridge struct {
    relay *ScopedRelay
    bridge *ReadOnlyBridge
}

func (r *ScopedRelay) NewBridge(consumer string) (*ScopedBridge,error) {
    if r==nil || r.stale || !r.started {return nil,ErrRelayStale}
    bridge,err:=NewReadOnlyBridge(r.ring,consumer)
    if err!=nil{return nil,err}
    return &ScopedBridge{relay:r,bridge:bridge},nil
}
func (b *ScopedBridge) Poll(max int) ([]InspectionHint,error) {
    if b==nil || b.relay==nil || b.relay.stale {
        return nil,ErrReinspectionRequired
    }
    return b.bridge.Poll(max)
}
func (b *ScopedBridge) Close() {
    if b!=nil && b.bridge!=nil {b.bridge.Close()}
}
