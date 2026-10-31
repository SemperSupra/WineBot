// SPDX-License-Identifier: MIT
// Test-only, read-only fanout; no HWND resolution or actuation authority.
package observercontract

import "errors"

var ErrCursorGap = errors.New("cursor_gap")
var ErrCursorUnknown = errors.New("cursor_unknown")
var ErrCursorDuplicate = errors.New("cursor_duplicate")

// Fanout keeps a bounded shared observation ring and independent consumer cursors.
// All mutation must be serialized by its owning supervisor; not concurrency-safe.
// An event does not carry a target identity or authorization.
type Fanout struct {
    cap int
    first uint64
    next uint64
    events []Frame
    cursors map[string]uint64
}

func NewFanout(capacity int) (*Fanout,error) {
    if capacity < 1 || capacity > 4096 { return nil,ErrInvalid }
    return &Fanout{cap:capacity,first:1,next:1,cursors:map[string]uint64{}},nil
}

func (f *Fanout) Subscribe(id string) error {
    if id=="" || len(id)>96 {return ErrInvalid}
    if _,exists:=f.cursors[id];exists{return ErrCursorDuplicate}
    f.cursors[id]=f.next
    return nil
}
func (f *Fanout) Unsubscribe(id string) {delete(f.cursors,id)}
func (f *Fanout) Publish(frame Frame) error {
    if frame.Contract!=Contract || frame.Stream=="" || frame.Source=="" {return ErrInvalid}
    if frame.Status!="ready" && frame.Status!="observed" && frame.Status!="gap" && frame.Status!="overflow" && frame.Status!="unsupported" {return ErrInvalid}
    f.events=append(f.events,frame)
    f.next++
    if len(f.events)>f.cap {
        f.events=f.events[1:]
        f.first++
    }
    return nil
}
func (f *Fanout) Poll(id string,max int) ([]Frame,error) {
    at,ok:=f.cursors[id]
    if !ok {return nil,ErrCursorUnknown}
    if max<1 || max>4096 {return nil,ErrInvalid}
    if at<f.first {
        // Fail closed. Consumer must re-subscribe and reconcile a fresh snapshot.
        return nil,ErrCursorGap
    }
    if at>=f.next {return []Frame{},nil}
    count:=int(f.next-at)
    if count>max {count=max}
    offset:=int(at-f.first)
    result:=append([]Frame(nil),f.events[offset:offset+count]...)
    f.cursors[id]=at+uint64(count)
    return result,nil
}
