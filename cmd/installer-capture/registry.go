// Offline conservative interpretation of Wine's native WINE REGISTRY Version 2
// files. Unlike a file-byte diff, this ignores timestamps and key ordering.
// Outputs still expose registry key/value names; never upload real results to
// public CI. Unhandled constructs fail closed instead of being silently lost.
package main

import (
 "bufio"
 "crypto/sha256"
 "encoding/hex"
 "errors"
 "fmt"
 "io"
 "os"
 "path/filepath"
 "regexp"
 "sort"
 "strings"
 "unicode/utf8"
)

const registryMaxBytes = 32 << 20
const registryMaxLine = 8 << 20
const registryMaxRecords = 250000

type RegistryRecord struct {
 Key string `json:"key"`
 Name string `json:"name,omitempty"`
 Kind string `json:"kind"`
 Type string `json:"type,omitempty"`
 Digest string `json:"sha256,omitempty"`
}
type RegistrySnapshot struct {
 Schema int `json:"schema"`
 Root string `json:"root"`
 Arch string `json:"arch"`
 Records []RegistryRecord `json:"records"`
}
type RegistryChange struct {
 Key string `json:"key"`
 Name string `json:"name,omitempty"`
 Operation string `json:"operation"`
 Before *RegistryRecord `json:"before,omitempty"`
 After *RegistryRecord `json:"after,omitempty"`
}
type RegistryDelta struct {
 Schema int `json:"schema"`
 Root string `json:"root"`
 Arch string `json:"arch"`
 Changes []RegistryChange `json:"changes"`
}

var (
 regKeyLine = regexp.MustCompile(`^\[(.+)\](?:[ \t]+[0-9]+)?$`)
 regValueLine = regexp.MustCompile(`^("(?:\\.|[^"\\])*"|@)=(.*)$`)
 regQuoted = regexp.MustCompile(`^"(?:\\.|[^"\\])*"$`)
 regDWORD = regexp.MustCompile(`^[0-9a-fA-F]{8}$`)
 regType = regexp.MustCompile(`^(str|hex)\(([0-9a-fA-F]+)\):(.*)$`)
 regHexBytes = regexp.MustCompile(`^(?:[0-9a-fA-F]{2}(?:,[0-9a-fA-F]{2})*,?)?$`)
)

func readPrivateRegistry(filename string) (RegistrySnapshot, error) {
 result := RegistrySnapshot{Schema: schemaVersion, Records: []RegistryRecord{}}
 // No symlink to a different path: a user-supplied manifest is not authority.
 dir, err := os.OpenRoot(filepath.Dir(filename))
 if err != nil { return result, errors.New("registry parent unavailable") }
 defer dir.Close()
 base := filepath.Base(filename)
 info, err := dir.Lstat(base)
 if err != nil || !info.Mode().IsRegular() || info.Size() > registryMaxBytes {
  return result, errors.New("registry file invalid or oversized")
 }
 f, err := dir.Open(base)
 if err != nil { return result, errors.New("registry file unavailable") }
 defer f.Close()
 opened, err := f.Stat()
 if err != nil || !os.SameFile(info, opened) { return result, errors.New("registry file changed") }
 return parseWineRegistry(io.LimitReader(f, registryMaxBytes+1))
}

func parseWineRegistry(reader io.Reader) (RegistrySnapshot, error) {
 result := RegistrySnapshot{Schema: schemaVersion, Records: []RegistryRecord{}}
 scanner := bufio.NewScanner(reader)
 scanner.Buffer(make([]byte, 4096), registryMaxLine)
 lineNo := 0
 header := false
 currentKey := ""
 seen := map[string]bool{}
 for scanner.Scan() {
  lineNo++
  line := strings.TrimSuffix(scanner.Text(), "\r")
  if !utf8.ValidString(line) { return result, errors.New("invalid registry encoding") }
  if len(line) > registryMaxLine-1 { return result, errors.New("registry line too large") }
  if lineNo == 1 {
   if line != "WINE REGISTRY Version 2" { return result, errors.New("unsupported registry format") }
   header = true
   continue
  }
  trimmed := strings.TrimSpace(line)
  if trimmed == "" { continue }
  if strings.HasPrefix(trimmed, ";; All keys relative to ") {
   root := strings.TrimPrefix(trimmed, ";; All keys relative to ")
   if result.Root != "" && result.Root != root { return result, errors.New("conflicting root") }
   result.Root = root
   continue
  }
  if strings.HasPrefix(trimmed, "#arch=") {
   arch := strings.TrimPrefix(trimmed, "#arch=")
   if arch != "win32" && arch != "win64" { return result, errors.New("unsupported registry arch") }
   if result.Arch != "" && result.Arch != arch { return result, errors.New("conflicting registry arch") }
   result.Arch = arch
   continue
  }
  if strings.HasPrefix(trimmed, "#") || strings.HasPrefix(trimmed, ";") { continue }
  if match := regKeyLine.FindStringSubmatch(trimmed); match != nil {
   currentKey = match[1]
   if len(currentKey) > 4096 { return result, errors.New("registry key too large") }
   id := "K\x00"+currentKey
   if seen[id] { return result, errors.New("duplicate registry key") }
   seen[id] = true
   result.Records = append(result.Records, RegistryRecord{Key: currentKey, Kind: "key"})
  } else if match := regValueLine.FindStringSubmatch(trimmed); match != nil {
   if currentKey == "" { return result, errors.New("registry value outside key") }
   name := match[1]
   if name == "@" { name = "" } else { name = name[1:len(name)-1] }
   if len(name) > 4096 { return result, errors.New("registry value name too large") }
   value := match[2]
   for strings.HasSuffix(strings.TrimRight(value, " \t"), "\\") {
    value = strings.TrimRight(value, " \t")
    value = strings.TrimSuffix(value, "\\")
    if !scanner.Scan() { return result, errors.New("unterminated registry continuation") }
    lineNo++
    continuation := strings.TrimSuffix(scanner.Text(), "\r")
    if !utf8.ValidString(continuation) { return result, errors.New("invalid registry continuation") }
    value += strings.TrimSpace(continuation)
    if len(value) > registryMaxLine { return result, errors.New("registry value too large") }
   }
   typ, canonical, err := parseRegistryValue(value)
   if err != nil { return result, err }
   key := "V\x00"+currentKey+"\x00"+name
   if seen[key] { return result, errors.New("duplicate registry value") }
   seen[key] = true
   hash := sha256.Sum256([]byte(typ+"\x00"+canonical))
   result.Records = append(result.Records, RegistryRecord{
    Key: currentKey, Name: name, Kind: "value", Type: typ, Digest: hex.EncodeToString(hash[:]),
   })
  } else {
   return result, fmt.Errorf("unsupported registry statement on line %d", lineNo)
  }
  if len(result.Records) > registryMaxRecords { return result, errors.New("registry record limit") }
 }
 if err := scanner.Err(); err != nil { return result, errors.New("registry reader failure") }
 if !header || result.Root == "" { return result, errors.New("registry header/root missing") }
 sort.Slice(result.Records, func(i,j int) bool { return registryID(result.Records[i]) < registryID(result.Records[j]) })
 return result, nil
}

func parseRegistryValue(v string) (string,string,error) {
 if regQuoted.MatchString(v) { return "sz",v,nil }
 if strings.HasPrefix(v, "dword:") {
  x:=strings.TrimPrefix(v, "dword:")
  if !regDWORD.MatchString(x) { return "","",errors.New("invalid registry DWORD") }
  return "dword",strings.ToLower(x),nil
 }
 if strings.HasPrefix(v,"hex:") {
  x:=strings.ReplaceAll(strings.TrimPrefix(v,"hex:")," ","")
  if !regHexBytes.MatchString(x) { return "","",errors.New("invalid registry hex") }
  return "hex",strings.ToLower(strings.TrimSuffix(x,",")),nil
 }
 if match:=regType.FindStringSubmatch(v);match!=nil {
  typ:=match[1]+"("+strings.ToLower(match[2])+")"
  val:=match[3]
  if match[1]=="str" {
   if !regQuoted.MatchString(val) { return "","",errors.New("invalid registry typed string") }
   return typ,val,nil
  }
  val=strings.ReplaceAll(val," ","")
  if !regHexBytes.MatchString(val) { return "","",errors.New("invalid registry typed hex") }
  return typ,strings.ToLower(strings.TrimSuffix(val,",")),nil
 }
 return "","",errors.New("unsupported registry value encoding")
}

// RegistrySummary exposes only fixed-domain counts for safe public review.
// The original registry delta retains full private keys and value names.
type RegistrySummaryRow struct {
 Operation string `json:"operation"`
 Keys int `json:"keys"`
 Values int `json:"values"`
}
type RegistrySummary struct {
 Schema int `json:"schema"`
 Groups []RegistrySummaryRow `json:"groups"`
}

func registrySummary(d RegistryDelta) (RegistrySummary, error) {
 out := RegistrySummary{Schema:schemaVersion,Groups:[]RegistrySummaryRow{}}
 if d.Schema!=schemaVersion || len(d.Changes)>registryMaxRecords*2 {
  return out, errors.New("invalid registry delta")
 }
 for _,operation := range []string{"added","removed","changed"} {
  row:=RegistrySummaryRow{Operation:operation}
  for _,change:=range d.Changes {
   if change.Operation!=operation {continue}
   var record *RegistryRecord
   if change.After!=nil {record=change.After} else {record=change.Before}
   if record==nil || record.Key=="" || change.Key!=record.Key ||
    change.Name!=record.Name {
    return out, errors.New("invalid registry summary source")
   }
   switch record.Kind {
   case "key": row.Keys++
   case "value": row.Values++
   default: return out, errors.New("invalid registry record class")
   }
  }
  out.Groups=append(out.Groups,row)
 }
 // No silent omission of unsupported operation labels.
 for _,change:=range d.Changes {
  if change.Operation!="added" && change.Operation!="removed" &&
   change.Operation!="changed" {return out,errors.New("invalid registry operation")}
 }
 return out,nil
}

func registryID(r RegistryRecord) string {
 return r.Kind+"\x00"+r.Key+"\x00"+r.Name
}
func diffRegistry(before, after RegistrySnapshot) (RegistryDelta,error) {
 d:=RegistryDelta{Schema:schemaVersion,Root:before.Root,Arch:before.Arch,Changes:[]RegistryChange{}}
 if before.Schema!=schemaVersion || after.Schema!=schemaVersion || before.Root=="" ||
    before.Root!=after.Root || before.Arch!=after.Arch {
  return d,errors.New("registry root, arch or schema mismatch")
 }
 a,b:=map[string]RegistryRecord{},map[string]RegistryRecord{}
 keys:=map[string]bool{}
 for _,r:=range before.Records {id:=registryID(r);if _,ok:=a[id];ok{return d,errors.New("duplicate before record")};a[id]=r;keys[id]=true}
 for _,r:=range after.Records {id:=registryID(r);if _,ok:=b[id];ok{return d,errors.New("duplicate after record")};b[id]=r;keys[id]=true}
 names:=make([]string,0,len(keys))
 for id:=range keys {names=append(names,id)}
 sort.Strings(names)
 for _,id:=range names {
  x,had:=a[id];y,has:=b[id]
  if had && has && x==y {continue}
  c:=RegistryChange{}
  if had {c.Key=x.Key;c.Name=x.Name;copy:=x;c.Before=&copy}
  if has {c.Key=y.Key;c.Name=y.Name;copy:=y;c.After=&copy}
  switch {case !had:c.Operation="added";case !has:c.Operation="removed";default:c.Operation="changed"}
  d.Changes=append(d.Changes,c)
 }
 return d,nil
}
