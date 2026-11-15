package main

import (
 "crypto/sha256"
 "encoding/hex"
 "encoding/json"
 "os"
 "path/filepath"
 "strings"
 "syscall"
 "testing"
)

func TestSnapshotDiffOffline(t *testing.T) {
 dir := t.TempDir()
 root := filepath.Join(dir, "prefix")
 if err := os.MkdirAll(filepath.Join(root, "drive_c"), 0700); err != nil { t.Fatal(err) }
 old := filepath.Join(root, "drive_c", "old.exe")
 changed := filepath.Join(root, "user.reg")
 if err := os.WriteFile(old, []byte("old file"), 0600); err != nil { t.Fatal(err) }
 if err := os.WriteFile(changed, []byte("registry BEFORE_SECRET_VALUE"), 0600); err != nil { t.Fatal(err) }
 a, err := snapshot(root)
 if err != nil { t.Fatal(err) }
 if err := os.Remove(old); err != nil { t.Fatal(err) }
 if err := os.WriteFile(changed, []byte("registry AFTER_SECRET_VALUE"), 0600); err != nil { t.Fatal(err) }
 if err := os.WriteFile(filepath.Join(root, "drive_c", "installed.exe"), []byte("new"), 0600); err != nil { t.Fatal(err) }
 if err := os.Symlink("/private/host/path", filepath.Join(root, "dosdevices")); err != nil { t.Fatal(err) }
 b, err := snapshot(root)
 if err != nil { t.Fatal(err) }
 d, err := delta(a, b)
 if err != nil { t.Fatal(err) }
 got := map[string]string{}
 for _, c := range d.Changes { got[c.Path] = c.Operation }
 for p, op := range map[string]string{"drive_c/old.exe":"removed","user.reg":"changed","drive_c/installed.exe":"added","dosdevices":"added"} {
  if got[p] != op { t.Fatalf("change %s = %s; want %s", p, got[p], op) }
 }
 raw, err := json.Marshal(b)
 if err != nil { t.Fatal(err) }
 if strings.Contains(string(raw), "SECRET_VALUE") || strings.Contains(string(raw), "/private/host/path") {
  t.Fatal("snapshot leaked content or raw symlink target")
 }
 first, err := snapshot(root)
 if err != nil { t.Fatal(err) }
 j, _ := json.Marshal(b)
 k, _ := json.Marshal(first)
 if string(j) != string(k) { t.Fatal("non-deterministic snapshot") }
}

func TestCLIAndPrivateOutput(t *testing.T) {
 dir := t.TempDir()
 root := filepath.Join(dir, "prefix")
 if err := os.Mkdir(root, 0700); err != nil { t.Fatal(err) }
 cwd, err := os.Getwd()
 if err != nil { t.Fatal(err) }
 relativeRoot, err := filepath.Rel(cwd, root)
 if err != nil { t.Fatal(err) }
 if !outOutsideRoot(relativeRoot, filepath.Join(dir, "before.json")) { t.Fatal("relative root should be supported") }
 if err := os.WriteFile(filepath.Join(root, "sample.reg"), []byte("value"), 0600); err != nil { t.Fatal(err) }
 inside := filepath.Join(root, "manifest.json")
 if err := run([]string{"snapshot", "-root", root, "-out", inside}); err == nil { t.Fatal("output inside root accepted") }
 before := filepath.Join(dir, "before.json")
 if err := run([]string{"snapshot", "-root", root, "-out", before}); err != nil { t.Fatal(err) }
 if err := run([]string{"snapshot", "-root", root, "-out", before}); err == nil { t.Fatal("overwrote existing snapshot") }
 st, err := os.Stat(before)
 if err != nil { t.Fatal(err) }
 if st.Mode().Perm() != 0600 { t.Fatalf("snapshot permissions %v", st.Mode()) }
 after := filepath.Join(dir, "after.json")
 if err := run([]string{"snapshot", "-root", root, "-out", after}); err != nil { t.Fatal(err) }
 deltaPath := filepath.Join(dir, "delta.json")
 if err := run([]string{"diff", "-before", before, "-after", after, "-out", deltaPath}); err != nil { t.Fatal(err) }
 data, err := os.ReadFile(deltaPath)
 if err != nil { t.Fatal(err) }
 var d Delta
 if err := json.Unmarshal(data, &d); err != nil { t.Fatal(err) }
 if len(d.Changes) != 0 { t.Fatalf("unchanged prefix has %d changes", len(d.Changes)) }
}

func TestRejectMaliciousManifest(t *testing.T) {
 h := strings.Repeat("a", 64)
 cases := []Manifest{
  {Schema: 2},
  {Schema: 1, Entries: []Entry{{Path:"../etc/passwd",Kind:"file",SHA256:h}}},
  {Schema: 1, Entries: []Entry{{Path:"file",Kind:"file",SHA256:h},{Path:"file",Kind:"file",SHA256:h}}},
  {Schema: 1, Entries: []Entry{{Path:"foo\\bar",Kind:"dir"}}},
  {Schema: 1, Entries: []Entry{{Path:"foo",Kind:"socket"}}},
  {Schema: 1, Entries: []Entry{{Path:"foo",Kind:"file",SHA256:"not-a-digest"}}},
 }
 for n, m := range cases { if validateManifest(m) == nil { t.Fatalf("invalid manifest %d accepted", n) } }
}

func TestFailClosedSpecialObjects(t *testing.T) {
 root := t.TempDir()
 // A dangling link must be recorded as metadata without being followed.
 if err := os.Symlink("/does/not/exist", filepath.Join(root, "external")); err != nil { t.Fatal(err) }
 m, err := snapshot(root)
 if err != nil { t.Fatal(err) }
 if len(m.Entries) != 1 || m.Entries[0].Kind != "symlink" { t.Fatalf("symlink not recorded correctly: %+v", m) }
}

func TestRejectFIFOWithoutBlocking(t *testing.T) {
 root := t.TempDir()
 fifo := filepath.Join(root, "transient-pipe")
 if err := syscall.Mkfifo(fifo, 0600); err != nil { t.Skipf("named pipes unsupported: %v", err) }
 if _, err := snapshot(root); err == nil { t.Fatal("named pipe accepted as a regular installation file") }
}


func TestConfinedSnapshotNeverHashesOutsideSymlink(t *testing.T) {
 root := t.TempDir()
 outside := t.TempDir()
 canary := "PRIVATE_OUTSIDE_CONTENT_CANARY"
 if err := os.WriteFile(filepath.Join(outside, "sensitive.txt"), []byte(canary), 0600); err != nil { t.Fatal(err) }
 if err := os.Symlink(outside, filepath.Join(root, "escape")); err != nil { t.Skipf("symlink unsupported: %v", err) }
 m, err := snapshot(root)
 if err != nil { t.Fatal(err) }
 if len(m.Entries) != 1 || m.Entries[0].Path != "escape" || m.Entries[0].Kind != "symlink" {
  t.Fatalf("outside symlink must be metadata-only: %+v", m)
 }
 b, err := json.Marshal(m)
 if err != nil { t.Fatal(err) }
 contentHash := sha256.Sum256([]byte(canary))
 if strings.Contains(string(b), hex.EncodeToString(contentHash[:])) ||
    strings.Contains(string(b), "sensitive.txt") || strings.Contains(string(b), canary) {
  t.Fatal("outside file was scanned")
 }
}
