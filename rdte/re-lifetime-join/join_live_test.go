// SPDX-License-Identifier: MIT
package rejoin

import (
    "os"
    "testing"
)

const pinnedSourceWine11Fixture = "858121cb3cb2bbf2196869b8befef302efd143dd"

// This test runs only when the exact Wine11 source-builder checkout has
// produced ephemeral evidence. It never echoes raw addresses or trace text.
// A source SHA literal is still not independent runtime provenance attestation.
func TestPinnedWine11RuntimeJoin(t *testing.T) {
    witnessPath := os.Getenv("WINE11_JOIN_WITNESS")
    tracePath := os.Getenv("WINE11_JOIN_TRACE")
    if witnessPath == "" && tracePath == "" {
        t.Skip("source Wine11 runtime input not provided")
    }
    if witnessPath == "" || tracePath == "" {
        t.Fatal("incomplete synthetic Wine11 stream inputs")
    }
    witness, err := os.Open(witnessPath)
    if err != nil {
        t.Fatal("unavailable bounded synthetic Wine11 witness")
    }
    defer witness.Close()
    trace, err := os.Open(tracePath)
    if err != nil {
        t.Fatal("unavailable bounded synthetic Wine11 heap trace")
    }
    defer trace.Close()

    result, err := VerifySyntheticLifetimeJoin(witness, trace, pinnedSourceWine11Fixture)
    if err != nil {
        t.Fatal("actual synthetic Wine11 witness/heap join refused")
    }
    if result.Schema != ReceiptSchema ||
        result.SourceCommit != pinnedSourceWine11Fixture ||
        result.WitnessRecords != 3 ||
        result.EvidenceClass != "SYNTHETIC_CONSISTENCY_ONLY" ||
        result.Trust != "UNVERIFIED" ||
        result.ProcessAttribution != "UNKNOWN" ||
        result.TraceCompleteness != "UNKNOWN" ||
        result.ClockCorrelation != "UNAVAILABLE" ||
        result.SemanticIdentity != "UNKNOWN" {
        t.Fatal("unsupported provenance or semantic claim")
    }
}
