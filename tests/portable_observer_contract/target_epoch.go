// SPDX-License-Identifier: MIT
// Experimental, synthetic-only supervisor-issued target epoch oracle.
// No Win32 handles, application identifiers, native event correlation or actuation.
package observercontract

import (
    "errors"
    "regexp"
)

var (
    ErrTargetInvalid = errors.New("target_invalid")
    ErrTargetStale = errors.New("target_stale")
    ErrTargetDuplicate = errors.New("target_duplicate")
)

// TargetStamp is an opaque reference only if a separately trusted supervisor
// minted the reference. It is not proof of HWND, PID, ownership, or authorization.
type TargetStamp struct {
    Session string
    Desktop string
    Producer string
    Generation uint64
    Ref string
    Epoch uint64
}

// TargetRegistry models a single stream producer's target lifetimes.
// Single-writer only. Observations must not create stamps implicitly.
type TargetRegistry struct {
    session string
    desktop string
    producer string
    generation uint64
    nextEpoch uint64
    active map[string]TargetStamp
}

var syntheticOpaqueRef = regexp.MustCompile(`^[A-Za-z0-9_-]{24,64}$`)

func NewTargetRegistry(session, desktop, producer string, generation uint64) (*TargetRegistry, error) {
    if session == "" || desktop == "" || producer == "" ||
        len(session) > 96 || len(desktop) > 96 || len(producer) > 96 ||
        generation == 0 {
        return nil, ErrTargetInvalid
    }
    return &TargetRegistry{
        session: session, desktop: desktop, producer: producer,
        generation: generation, active: make(map[string]TargetStamp),
    }, nil
}

// Rotate invalidates every reference, even if the same synthetic opaque ref is
// later issued again. Generation must be strictly increasing (no ABA/replay).
func (r *TargetRegistry) Rotate(next uint64) error {
    if r == nil || next == 0 || next <= r.generation { return ErrTargetStale }
    r.generation = next
    r.active = make(map[string]TargetStamp)
    return nil
}

// BindTrustedRef assumes a separate trusted supervisor has already verified
// target provenance and minted a non-identifying opaque ref. This synthetic
// oracle explicitly does NOT perform such attestation.
func (r *TargetRegistry) BindTrustedRef(ref string) (TargetStamp, error) {
    if r == nil || !syntheticOpaqueRef.MatchString(ref) ||
        r.nextEpoch == ^uint64(0) {
        return TargetStamp{}, ErrTargetInvalid
    }
    if _, exists := r.active[ref]; exists { return TargetStamp{}, ErrTargetDuplicate }
    r.nextEpoch++
    stamp := TargetStamp{
        Session: r.session, Desktop: r.desktop, Producer: r.producer,
        Generation: r.generation, Ref: ref, Epoch: r.nextEpoch,
    }
    r.active[ref] = stamp
    return stamp, nil
}

// Check proves only current registry consistency, not authority to actuate.
func (r *TargetRegistry) Check(s TargetStamp) error {
    if r == nil || s.Session != r.session || s.Desktop != r.desktop ||
        s.Producer != r.producer || s.Generation != r.generation ||
        s.Epoch == 0 || s.Ref == "" {
        return ErrTargetStale
    }
    live, ok := r.active[s.Ref]
    if !ok || live != s { return ErrTargetStale }
    return nil
}

func (r *TargetRegistry) Revoke(s TargetStamp) error {
    if err := r.Check(s); err != nil { return err }
    delete(r.active, s.Ref)
    return nil
}
