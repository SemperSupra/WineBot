// WineBot installer-capture: source-only, offline prefix inventory research tool.
// Snapshots contain path names and hashes, which may be sensitive. Never publish
// real prefix snapshots or diffs as public CI artifacts.
package main

import (
 "crypto/sha256"
 "encoding/hex"
 "encoding/json"
 "errors"
 "flag"
 "fmt"
 "io"
 "io/fs"
 "os"
 "path"
 "path/filepath"
 "reflect"
 "sort"
 "strings"
)

const schemaVersion = 1
const maxEntries = 250000
const maxManifestBytes = 64 << 20

type Entry struct {
 Path string `json:"path"`
 Kind string `json:"kind"`
 Size int64 `json:"size,omitempty"`
 SHA256 string `json:"sha256,omitempty"`
}
type Manifest struct {
 Schema int `json:"schema"`
 Entries []Entry `json:"entries"`
}
type Change struct {
 Path string `json:"path"`
 Operation string `json:"operation"`
 Before *Entry `json:"before,omitempty"`
 After *Entry `json:"after,omitempty"`
}
type Delta struct {
 Schema int `json:"schema"`
 Changes []Change `json:"changes"`
}

func validPath(p string) bool {
 return p != "" && p != "." && !strings.Contains(p, "\\") &&
  !strings.HasPrefix(p, "/") && path.Clean(p) == p &&
  !strings.HasPrefix(p, "../") && p != ".."
}
func validHash(v string) bool {
 if len(v) != 64 { return false }
 b, err := hex.DecodeString(v)
 return err == nil && hex.EncodeToString(b) == v
}
func validateManifest(m Manifest) error {
 if m.Schema != schemaVersion || len(m.Entries) > maxEntries { return errors.New("manifest schema or entry count") }
 seen := map[string]bool{}
 for _, e := range m.Entries {
  if !validPath(e.Path) || seen[e.Path] { return errors.New("manifest path") }
  seen[e.Path] = true
  switch e.Kind {
  case "file": if e.Size < 0 || !validHash(e.SHA256) { return errors.New("manifest file") }
  case "symlink": if e.Size != 0 || !validHash(e.SHA256) { return errors.New("manifest symlink") }
  case "dir": if e.Size != 0 || e.SHA256 != "" { return errors.New("manifest dir") }
  default: return errors.New("manifest type")
  }
 }
 return nil
}
func snapshot(root string) (Manifest, error) {
 m := Manifest{Schema: schemaVersion, Entries: []Entry{}}
 canonical, err := filepath.EvalSymlinks(root)
 if err != nil { return m, err }
 info, err := os.Stat(canonical)
 if err != nil || !info.IsDir() { return m, errors.New("root must exist and be directory") }
 err = filepath.WalkDir(canonical, func(p string, d fs.DirEntry, incoming error) error {
  if incoming != nil { return incoming }
  if p == canonical { return nil }
  if len(m.Entries) >= maxEntries { return errors.New("entry limit reached") }
  rel, err := filepath.Rel(canonical, p)
  if err != nil { return err }
  name := filepath.ToSlash(rel)
  if !validPath(name) { return errors.New("invalid relative path") }
  e := Entry{Path: name}
  switch {
  case d.Type().IsRegular():
   file, err := os.Open(p)
   if err != nil { return err }
   before, err := file.Stat()
   if err != nil { file.Close(); return err }
   h := sha256.New()
   n, err := io.Copy(h, file)
   after, statErr := file.Stat()
   closeErr := file.Close()
   if err != nil { return err }
   if statErr != nil { return statErr }
   if closeErr != nil { return closeErr }
   if n != before.Size() || n != after.Size() || !before.ModTime().Equal(after.ModTime()) {
    return errors.New("file changed during snapshot; quiesce the prefix")
   }
   e.Kind, e.Size, e.SHA256 = "file", n, hex.EncodeToString(h.Sum(nil))
  case d.IsDir():
   e.Kind = "dir"
  case d.Type()&os.ModeSymlink != 0:
   target, err := os.Readlink(p)
   if err != nil { return err }
   sum := sha256.Sum256([]byte(target))
   e.Kind, e.SHA256 = "symlink", hex.EncodeToString(sum[:])
  default:
   return errors.New("unsupported object; quiesce prefix and remove transient sockets")
  }
  m.Entries = append(m.Entries, e)
  return nil
 })
 if err != nil { return Manifest{}, err }
 sort.Slice(m.Entries, func(i, j int) bool { return m.Entries[i].Path < m.Entries[j].Path })
 return m, validateManifest(m)
}
func readManifest(filename string) (Manifest, error) {
 m := Manifest{}
 f, err := os.Open(filename)
 if err != nil { return m, err }
 defer f.Close()
 info, err := f.Stat()
 if err != nil { return m, err }
 if info.Size() > maxManifestBytes { return m, errors.New("manifest too large") }
 dec := json.NewDecoder(io.LimitReader(f, maxManifestBytes+1))
 dec.DisallowUnknownFields()
 if err := dec.Decode(&m); err != nil { return m, err }
 var next any
 if err := dec.Decode(&next); err != io.EOF { return m, errors.New("trailing manifest data") }
 return m, validateManifest(m)
}
func delta(before, after Manifest) (Delta, error) {
 result := Delta{Schema: schemaVersion, Changes: []Change{}}
 if err := validateManifest(before); err != nil { return result, err }
 if err := validateManifest(after); err != nil { return result, err }
 old, now := map[string]Entry{}, map[string]Entry{}
 paths := map[string]bool{}
 for _, e := range before.Entries { old[e.Path] = e; paths[e.Path] = true }
 for _, e := range after.Entries { now[e.Path] = e; paths[e.Path] = true }
 names := make([]string, 0, len(paths))
 for p := range paths { names = append(names, p) }
 sort.Strings(names)
 for _, p := range names {
  a, had := old[p]
  b, has := now[p]
  if had && has && reflect.DeepEqual(a, b) { continue }
  c := Change{Path: p}
  if had { copyA := a; c.Before = &copyA }
  if has { copyB := b; c.After = &copyB }
  switch {
  case !had: c.Operation = "added"
  case !has: c.Operation = "removed"
  default: c.Operation = "changed"
  }
  result.Changes = append(result.Changes, c)
 }
 return result, nil
}
func writeJSON(out string, v any) error {
 // No output file inside a watched prefix is allowed at the CLI boundary.
 dir := filepath.Dir(out)
 f, err := os.CreateTemp(dir, ".winebot-capture-*")
 if err != nil { return err }
 name := f.Name()
 defer os.Remove(name)
 if err := f.Chmod(0600); err != nil { f.Close(); return err }
 enc := json.NewEncoder(f)
 enc.SetIndent("", "  ")
 if err := enc.Encode(v); err != nil { f.Close(); return err }
 if err := f.Sync(); err != nil { f.Close(); return err }
 if err := f.Close(); err != nil { return err }
 // Hard-link creation is atomic and refuses overwrite of an existing output.
 return os.Link(name, out)
}
func outOutsideRoot(root, out string) bool {
 r, err1 := filepath.EvalSymlinks(root)
 o, err2 := filepath.Abs(out)
 if err1 != nil || err2 != nil { return false }
 dir, err3 := filepath.EvalSymlinks(filepath.Dir(o))
 if err3 != nil { return false }
 relative, err4 := filepath.Rel(r, filepath.Join(dir, filepath.Base(o)))
 if err4 != nil { return false }
 return relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator))
}
func run(argv []string) error {
 if len(argv) == 0 { return errors.New("missing command") }
 switch argv[0] {
 case "snapshot":
  flags := flag.NewFlagSet("snapshot", flag.ContinueOnError)
  flags.SetOutput(io.Discard)
  root := flags.String("root", "", "quiesced Wine prefix root")
  out := flags.String("out", "", "private snapshot JSON outside root")
  if err := flags.Parse(argv[1:]); err != nil || flags.NArg() != 0 || *root == "" || *out == "" { return errors.New("invalid snapshot arguments") }
  if !outOutsideRoot(*root, *out) { return errors.New("snapshot output must be outside root") }
  m, err := snapshot(*root)
  if err != nil { return err }
  return writeJSON(*out, m)
 case "diff":
  flags := flag.NewFlagSet("diff", flag.ContinueOnError)
  flags.SetOutput(io.Discard)
  before := flags.String("before", "", "before JSON")
  after := flags.String("after", "", "after JSON")
  out := flags.String("out", "", "private delta JSON")
  if err := flags.Parse(argv[1:]); err != nil || flags.NArg() != 0 || *before == "" || *after == "" || *out == "" { return errors.New("invalid diff arguments") }
  if *out == *before || *out == *after { return errors.New("refuse overwrite of input") }
  a, err := readManifest(*before)
  if err != nil { return err }
  b, err := readManifest(*after)
  if err != nil { return err }
  d, err := delta(a, b)
  if err != nil { return err }
  return writeJSON(*out, d)
 default: return errors.New("unknown command")
 }
}
func main() {
 if err := run(os.Args[1:]); err != nil {
  // Fixed-category public messages. Do not print raw paths or raw errors.
  fmt.Fprintln(os.Stderr, "WINEBOT_CAPTURE status=failed")
  os.Exit(1)
 }
 fmt.Println("WINEBOT_CAPTURE status=passed")
}
