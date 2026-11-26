// SPDX-License-Identifier: MIT
// Synthetic-only correlation of current-state Win32 and Wine11 +heap evidence.
package rejoin

import (
	"errors"
	"io"

	evidence "../re-observation-contract"
	heaptrace "../wine11-heap-trace"
)

const maxWitnessBytes int64 = 12288
const ReceiptSchema = "winebot.research.synthetic-lifetime-join/v1"

// Receipt deliberately contains no address, heap handle, PID, raw trace,
// application-private type, or authenticated process identity.
// A syntactically consistent synthetic trace is NOT proof of provenance.
type Receipt struct {
	Schema             string `json:"schema"`
	Backend            string `json:"backend"`
	SourceCommit       string `json:"source_commit"`
	WitnessRecords     int    `json:"witness_records"`
	Join               string `json:"join"`
	EvidenceClass      string `json:"evidence_class"`
	SourceAttestation  string `json:"source_attestation"`
	ProcessAttribution string `json:"process_attribution"`
	TraceCompleteness  string `json:"trace_completeness"`
	ClockCorrelation   string `json:"clock_correlation"`
	SemanticIdentity   string `json:"semantic_identity"`
	Trust              string `json:"trust"`
}

// VerifySyntheticLifetimeJoin checks three strict current-state records AND
// one exact synthetic allocation->free trace of the same pointer and extent.
// Both input parsers retain their own budgets and adversarial controls.
// It never promotes synthetic consistency to LIVE or VERIFIED provenance.
// Caller must independently bind source SHA, fixture, runner and process.
func VerifySyntheticLifetimeJoin(witness, trace io.Reader, claimedSourceCommit string) (Receipt, error) {
	var empty Receipt
	if witness == nil || trace == nil {
		return empty, errors.New("missing_synthetic_inputs")
	}
	payload, err := io.ReadAll(io.LimitReader(witness, maxWitnessBytes+1))
	if err != nil || len(payload) == 0 || int64(len(payload)) > maxWitnessBytes {
		return empty, errors.New("invalid_bounded_wine11_witness")
	}
	records, err := evidence.NormalizeWine11CurrentStateWitness(payload, claimedSourceCommit)
	if err != nil || len(records) != 3 {
		return empty, errors.New("invalid_synthetic_current_state")
	}
	heap := records[1]
	if heap.Kind != "heap_allocation" || heap.Address == nil || heap.SizeBytes == nil {
		return empty, errors.New("missing_heap_allocation")
	}
	if err := heaptrace.VerifySyntheticLifetime(trace, *heap.Address, *heap.SizeBytes); err != nil {
		return empty, errors.New("invalid_synthetic_heap_lifetime")
	}
	return Receipt{
		Schema:             ReceiptSchema,
		Backend:            "wine",
		SourceCommit:       claimedSourceCommit,
		WitnessRecords:     len(records),
		Join:               "same_pointer_and_extent_alloc_then_free",
		EvidenceClass:      "SYNTHETIC_CONSISTENCY_ONLY",
		SourceAttestation:  "UNVERIFIED",
		ProcessAttribution: "UNKNOWN",
		TraceCompleteness:  "UNKNOWN",
		ClockCorrelation:   "UNAVAILABLE",
		SemanticIdentity:   "UNKNOWN",
		Trust:              "UNVERIFIED",
	}, nil
}
