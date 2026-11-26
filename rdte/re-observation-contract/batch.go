// SPDX-License-Identifier: MIT
package evidence

import "errors"

// ValidateOneSensorBatch binds a synthetic evidence batch to the independently
// supplied exact-source commit. A self-declared record SHA is not attestation.
// Different sensors/OS processes cannot be joined without a separate verified
// session correlation contract. This helper therefore rejects mixed providers.
func ValidateOneSensorBatch(records [][]byte, expectedCommit string) error {
	if !commitSHA.MatchString(expectedCommit) {
		return errors.New("invalid_expected_source")
	}
	if len(records) < 1 || len(records) > 16 {
		return errors.New("invalid_batch_size")
	}
	var original Observation
	seen := make(map[string]bool)
	for index, raw := range records {
		one, err := Validate(raw)
		if err != nil {
			return errors.New("invalid_batch_record")
		}
		if one.SourceCommit != expectedCommit {
			return errors.New("source_head_mismatch")
		}
		if index == 0 {
			original = one
		} else if one.Backend != original.Backend ||
			one.Sensor != original.Sensor ||
			one.ProcessID != original.ProcessID {
			return errors.New("mixed_process_or_sensor")
		}
		if seen[one.Kind] {
			return errors.New("duplicate_kind")
		}
		seen[one.Kind] = true
	}
	// An invented digest or a same-process guess does not prove a real
	// acquisition. Caller must independently verify Git ref and workflow run.
	return nil
}
