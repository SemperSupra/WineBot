// SPDX-License-Identifier: MIT
// Pure synthetic authorization reference: no platform input or actuation.
package observercontract

import "errors"

var (
 ErrUnauthorized = errors.New("actuation_unauthorized")
 ErrStaleTarget = errors.New("stale_target")
 ErrLeaseConflict = errors.New("desktop_lease_conflict")
 ErrOutcomeUnknown = errors.New("actuation_outcome_unknown")
)

type Proposal struct {
 Principal string
 Desktop string
 LeaseEpoch uint64
 TargetRef string
 TargetEpoch uint64
 Operation string
}

type Authority struct {
 Principal string
 Desktop string
 LeaseEpoch uint64
 TargetRef string
 TargetEpoch uint64
 Allowed map[string]bool
}

// ValidateProposal is a fail-closed preflight predicate only.
// Passing it is NOT permission to actuate: production requires an
// authenticated broker, serialized lease check and verified postcondition.
func ValidateProposal(p Proposal, a Authority) error {
 if p.Principal=="" || p.Desktop=="" || p.TargetRef=="" || p.Operation=="" {return ErrUnauthorized}
 if p.Principal!=a.Principal || p.Desktop!=a.Desktop {return ErrUnauthorized}
 if p.LeaseEpoch==0 || p.LeaseEpoch!=a.LeaseEpoch {return ErrLeaseConflict}
 if p.TargetEpoch==0 || p.TargetRef!=a.TargetRef || p.TargetEpoch!=a.TargetEpoch {return ErrStaleTarget}
 if !a.Allowed[p.Operation] {return ErrUnauthorized}
 return nil
}

// A successful command dispatch without an independently observed
// postcondition must never be reported as verified success.
func VerifyPostcondition(observed,expected string,observationCurrent bool) error {
 if !observationCurrent || observed=="" || expected=="" || observed!=expected {return ErrOutcomeUnknown}
 return nil
}
