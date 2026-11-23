// SPDX-License-Identifier: MIT
package evidence

import (
	"encoding/json"
	"strings"
	"testing"
)

func encodeTestRecord(t *testing.T, o Observation) []byte {
	t.Helper()
	data, err := json.Marshal(o)
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func TestOneSensorBatchValid(t *testing.T) {
	for _, sensor := range []string{"phnt", "traceevent", "win32_api"} {
		a := fixture(sensor)
		recs := [][]byte{encodeTestRecord(t, a)}
		if sensor == "phnt" {
			b := a
			b.Kind = "nt_process"
			recs = append(recs, encodeTestRecord(t, b))
		}
		if sensor == "win32_api" {
			b := a
			b.Kind = "memory_region"
			recs = append(recs, encodeTestRecord(t, b))
		}
		if err := ValidateOneSensorBatch(recs, strings.Repeat("a", 40)); err != nil {
			t.Fatalf("valid %s: %v", sensor, err)
		}
	}
}

func TestBatchRejectsFalseCorrelations(t *testing.T) {
	a := fixture("win32_api")
	b := a
	b.Kind = "module"
	good := encodeTestRecord(t, a)
	other := encodeTestRecord(t, b)
	bad := map[string][][]byte{
		"empty": {},
		"duplicate_kind": {good, good},
		"mixed_sensors": {good, encodeTestRecord(t, fixture("phnt"))},
		"bad_record": {good, []byte("{}")},
		"too_many": make([][]byte, 17),
	}
	for i := range bad["too_many"] {
		bad["too_many"][i] = good
	}
	b.ProcessID = 45
	bad["mixed_process"] = [][]byte{good, encodeTestRecord(t, b)}
	for name, input := range bad {
		t.Run(name, func(t *testing.T) {
			if err := ValidateOneSensorBatch(input, strings.Repeat("a", 40)); err == nil {
				t.Fatal("accepted unsupported mixed batch")
			}
		})
	}
	if err := ValidateOneSensorBatch([][]byte{good, other}, strings.Repeat("b", 40)); err == nil {
		t.Fatal("accepted mismatched exact source")
	}
	if err := ValidateOneSensorBatch([][]byte{good}, "unverified"); err == nil {
		t.Fatal("accepted invalid externally supplied digest")
	}
}
