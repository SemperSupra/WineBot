// SPDX-License-Identifier: MIT
package rejoin

import (
	"encoding/json"
	"fmt"
	"strings"
	"testing"
)

const syntheticSHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

func witnessRow(kind, address string, size, pid uint64) string {
	return fmt.Sprintf(
		"{\"schema\":\"wine-introspection-rdte/v0\",\"source\":\"WIN32_API_ENUMERATED\",\"kind\":%q,\"process_id\":%d,\"address_space\":\"windows_process_va\",\"address\":%q,\"size_bytes\":%d,\"object_id\":null,\"generation\":null,\"semantic_type\":null,\"snapshot\":\"best_effort\",\"coverage\":\"partial\"}",
		kind, pid, address, size,
	)
}

func validWitness() string {
	return witnessRow("module", "0x140000000", 8192, 42) + "\n" +
		witnessRow("heap_allocation", "0x200040", 256, 42) + "\n" +
		witnessRow("memory_region", "0x200000", 4096, 42) + "\n"
}

const alloc = "0034:trace:heap:RtlAllocateHeap handle 0xabc, flags 0, size 0x100, return 0x200040, status 0.\n"
const release = "0034:trace:heap:RtlFreeHeap handle 0xabc, flags 0, ptr 0x200040, return 1, status 0.\n"

func TestJoinedSyntheticWine11Evidence(t *testing.T) {
	got, err := VerifySyntheticLifetimeJoin(strings.NewReader(validWitness()), strings.NewReader(alloc+release), syntheticSHA)
	if err != nil {
		t.Fatalf("original bounded fixture rejected: %v", err)
	}
	if got.Schema != ReceiptSchema || got.WitnessRecords != 3 ||
		got.EvidenceClass != "SYNTHETIC_CONSISTENCY_ONLY" ||
		got.Trust != "UNVERIFIED" || got.SourceAttestation != "UNVERIFIED" ||
		got.ProcessAttribution != "UNKNOWN" || got.TraceCompleteness != "UNKNOWN" ||
		got.SemanticIdentity != "UNKNOWN" || got.ClockCorrelation != "UNAVAILABLE" {
		t.Fatal("joined result made an unsupported assurance or omitted required uncertainty")
	}
	encoded, err := json.Marshal(got)
	if err != nil {
		t.Fatal(err)
	}
	for _, forbidden := range []string{"0x200040", "0xabc", "process_id", "semantic_type", "\"trust\":\"VERIFIED\""} {
		if strings.Contains(string(encoded), forbidden) {
			t.Fatal("receipt exposes raw witness or fabricates a verified live claim")
		}
	}
}

func TestJoinRefusesContradictoryInputs(t *testing.T) {
	good := validWitness()
	cases := map[string]struct {
		witness string
		trace   string
		commit  string
	}{
		"missing_free":        {good, alloc, syntheticSHA},
		"free_before_alloc":   {good, release+alloc, syntheticSHA},
		"wrong_trace_size":    {good, strings.Replace(alloc, "size 0x100", "size 0x80", 1)+release, syntheticSHA},
		"wrong_trace_pointer": {good, strings.Replace(alloc, "return 0x200040", "return 0x300040", 1)+release, syntheticSHA},
		"wrong_heap_handle":   {good, alloc+strings.Replace(release, "handle 0xabc", "handle 0xdef", 1), syntheticSHA},
		"duplicate_alloc":     {good, alloc+alloc+release, syntheticSHA},
		"duplicate_free":      {good, alloc+release+release, syntheticSHA},
		"failed_free":         {good, alloc+strings.Replace(release, "return 1", "return 0", 1), syntheticSHA},
		"mixed_witness_pid":   {strings.Replace(good, "\"process_id\":42", "\"process_id\":43", 1), alloc+release, syntheticSHA},
		"fabricated_type":     {strings.Replace(good, "\"semantic_type\":null", "\"semantic_type\":\"Widget\"", 1), alloc+release, syntheticSHA},
		"bad_address_domain":  {strings.Replace(good, "windows_process_va", "wineserver_host_va", 1), alloc+release, syntheticSHA},
		"duplicate_json_key":  {strings.Replace(good, "\"kind\":\"module\"", "\"kind\":\"module\",\"kind\":\"module\"", 1), alloc+release, syntheticSHA},
		"bad_region":         {strings.Replace(good, "\"address\":\"0x200000\"", "\"address\":\"0x800000\"", 1), alloc+release, syntheticSHA},
		"oversize_witness":    {strings.Repeat("x", int(maxWitnessBytes)+1), alloc+release, syntheticSHA},
		"oversize_trace":      {good, alloc+strings.Repeat("A", 8<<20)+release, syntheticSHA},
		"bad_commit":          {good, alloc+release, "not-a-source-ref"},
		"empty_witness":       {"", alloc+release, syntheticSHA},
		"empty_trace":         {good, "", syntheticSHA},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			receipt, err := VerifySyntheticLifetimeJoin(strings.NewReader(tc.witness), strings.NewReader(tc.trace), tc.commit)
			if err == nil || receipt.Schema != "" {
				t.Fatal("invalid synthetic join accepted or retained a partial receipt")
			}
			if strings.Contains(err.Error(), "0x200040") || strings.Contains(err.Error(), "0xabc") {
				t.Fatal("error leaked raw fixture memory addresses")
			}
		})
	}
	if _, err := VerifySyntheticLifetimeJoin(nil, strings.NewReader(alloc+release), syntheticSHA); err == nil {
		t.Fatal("nil witness accepted")
	}
	if _, err := VerifySyntheticLifetimeJoin(strings.NewReader(validWitness()), nil, syntheticSHA); err == nil {
		t.Fatal("nil trace accepted")
	}
}
