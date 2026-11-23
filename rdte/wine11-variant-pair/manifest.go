// SPDX-License-Identifier: MIT
// Synthetic-only contract for Wine 11 stock/instrumented comparison admissions.
package main

import (
    "bytes"
    "encoding/json"
    "errors"
    "fmt"
    "io"
    "regexp"
)

const maxRecordBytes = 8192

var digestPattern = regexp.MustCompile("^sha256:[0-9a-f]{64}$")
var buildFields = map[string]bool{
    "variant":true, "wine_version":true, "upstream_tag":true,
    "source_archive_digest":true, "toolchain_digest":true,
    "dependencies_digest":true, "patch_queue_digest":true,
    "image_digest":true, "sensor_mode":true,
}
var sessionFields = map[string]bool{
    "variant":true, "session_id":true, "generation":true,
    "fixture_digest":true, "prefix_origin":true, "prefix_clone_id":true,
    "source_snapshot_digest":true, "state_mount_id":true, "writable":true,
}

// Build is a declaration, NOT a signature or verified build attestation.
type Build struct {
    Variant string `json:"variant"`
    WineVersion string `json:"wine_version"`
    UpstreamTag string `json:"upstream_tag"`
    SourceArchiveDigest string `json:"source_archive_digest"`
    ToolchainDigest string `json:"toolchain_digest"`
    DependenciesDigest string `json:"dependencies_digest"`
    PatchQueueDigest string `json:"patch_queue_digest"`
    ImageDigest string `json:"image_digest"`
    SensorMode string `json:"sensor_mode"`
}

// Session is a proposed isolated run, NOT proof of mount or lease custody.
type Session struct {
    Variant string `json:"variant"`
    SessionID string `json:"session_id"`
    Generation uint64 `json:"generation"`
    FixtureDigest string `json:"fixture_digest"`
    PrefixOrigin string `json:"prefix_origin"`
    PrefixCloneID string `json:"prefix_clone_id"`
    SourceSnapshotDigest string `json:"source_snapshot_digest"`
    StateMountID string `json:"state_mount_id"`
    Writable bool `json:"writable"`
}

// strictRecord rejects duplicate JSON object keys, added fields, truncated and
// trailing records. Every admission document is a single flat object.
func strictRecord(r io.Reader, target any, allowed map[string]bool) error {
    payload, err := io.ReadAll(io.LimitReader(r, maxRecordBytes+1))
    if err != nil || len(payload) == 0 || len(payload) > maxRecordBytes {
        return errors.New("missing or oversized record")
    }
    d := json.NewDecoder(bytes.NewReader(payload))
    first, err := d.Token()
    if err != nil || first != json.Delim('{') {
        return errors.New("expected object")
    }
    seen := make(map[string]bool)
    for d.More() {
        token, err := d.Token()
        if err != nil {
            return errors.New("malformed object")
        }
        key, ok := token.(string)
        if !ok || seen[key] || !allowed[key] {
            return errors.New("duplicate or invalid field")
        }
        seen[key] = true
        var value json.RawMessage
        if err := d.Decode(&value); err != nil {
            return errors.New("malformed field")
        }
        if len(value) == 0 || value[0] == '{' || value[0] == '[' {
            return errors.New("nested evidence not admitted")
        }
    }
    if len(seen) != len(allowed) { return errors.New("missing required field") }
    end, err := d.Token()
    if err != nil || end != json.Delim('}') {
        return errors.New("malformed object end")
    }
    if _, err := d.Token(); err != io.EOF {
        return errors.New("trailing evidence")
    }
    typed := json.NewDecoder(bytes.NewReader(payload))
    typed.DisallowUnknownFields()
    if err := typed.Decode(target); err != nil {
        return errors.New("unknown field or invalid type")
    }
    return nil
}

func parseBuild(r io.Reader) (Build, error) {
    var b Build
    err := strictRecord(r, &b, buildFields)
    return b, err
}

func parseSession(r io.Reader) (Session, error) {
    var s Session
    err := strictRecord(r, &s, sessionFields)
    return s, err
}

func digest(v string) bool { return digestPattern.MatchString(v) }

func validateBuild(b Build, variant string) error {
    if b.Variant != variant || b.WineVersion != "11.0" ||
        b.UpstreamTag != "wine-11.0" {
        return errors.New("wrong variant or Wine 11 source identity")
    }
    if !digest(b.SourceArchiveDigest) || !digest(b.ToolchainDigest) ||
        !digest(b.DependenciesDigest) || !digest(b.ImageDigest) {
        return errors.New("incomplete digest declaration")
    }
    if variant == "stock" {
        if b.PatchQueueDigest != "" || b.SensorMode != "baseline" {
            return errors.New("stock must declare zero instrumentation patches")
        }
    } else if !digest(b.PatchQueueDigest) || b.SensorMode != "optional-native" {
        return errors.New("instrumented patch queue and sensor policy required")
    }
    return nil
}

func validateSession(s Session, variant string) error {
    if s.Variant != variant || s.SessionID == "" || s.Generation == 0 ||
        s.PrefixCloneID == "" || s.StateMountID == "" {
        return errors.New("incomplete session custody declaration")
    }
    if !digest(s.FixtureDigest) || !digest(s.SourceSnapshotDigest) {
        return errors.New("missing session baseline provenance")
    }
    if s.PrefixOrigin != "synthetic" && s.PrefixOrigin != "cloned" {
        return errors.New("live or unspecified user prefix is forbidden")
    }
    if !s.Writable {
        return errors.New("comparison requires declared isolated writable clone")
    }
    return nil
}

// validatePair establishes only structural admission preconditions. External
// custody must independently verify source hashes, OCI digests, real mount IDs,
// source state checksums, leases, build reproducibility and human STOP priority.
func validatePair(stock, instrumented Build, a, b Session) error {
    if err := validateBuild(stock, "stock"); err != nil { return fmt.Errorf("stock: %w", err) }
    if err := validateBuild(instrumented, "instrumented"); err != nil { return fmt.Errorf("instrumented: %w", err) }
    if stock.SourceArchiveDigest != instrumented.SourceArchiveDigest ||
        stock.ToolchainDigest != instrumented.ToolchainDigest ||
        stock.DependenciesDigest != instrumented.DependenciesDigest {
        return errors.New("different upstream source/build environment")
    }
    if stock.ImageDigest == instrumented.ImageDigest {
        return errors.New("different variants must have distinct image digests")
    }
    if err := validateSession(a, "stock"); err != nil { return fmt.Errorf("stock session: %w", err) }
    if err := validateSession(b, "instrumented"); err != nil { return fmt.Errorf("instrumented session: %w", err) }
    if a.FixtureDigest != b.FixtureDigest || a.SourceSnapshotDigest != b.SourceSnapshotDigest {
        return errors.New("comparison workloads or source snapshots differ")
    }
    if a.SessionID == b.SessionID || a.PrefixCloneID == b.PrefixCloneID ||
        a.StateMountID == b.StateMountID {
        return errors.New("shared session or writable state alias")
    }
    return nil
}
