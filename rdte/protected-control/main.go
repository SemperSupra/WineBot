//go:build linux

// An isolated, offline control-owner CAS reference. It is not wired to
// the WineBot runtime or exposed to any guest service.
package main

import (
 "bytes"
 "encoding/json"
 "errors"
 "fmt"
 "io"
 "os"
 "path/filepath"
 "regexp"
 "strconv"
 "syscall"
)

const (
 schemaV1 = "winebot/control-owner/v1"
 ownerName = ".winebot-owner-v1.json"
 lockName = ".winebot-owner-v1.lock"
 maxRecordBytes = 8192
 maxGeneration int64 = 9223372036854775807
)

var identifier = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$`)

type Record struct {
 Schema string `json:"schema"`
 Generation int64 `json:"generation"`
 SessionID string `json:"session_id"`
 OperationID string `json:"operation_id"`
}

func validateRoot(root string, uid uint32) (*os.File, error) {
 if !filepath.IsAbs(root) || filepath.Clean(root) != root { return nil, errors.New("invalid control root") }
 resolved, err := filepath.EvalSymlinks(root)
 if err != nil || resolved != root { return nil, errors.New("control root path rejected") }
 st, err := os.Lstat(root)
 if err != nil || !st.IsDir() || st.Mode().Perm() != 0700 { return nil, errors.New("control root permissions rejected") }
 raw, ok := st.Sys().(*syscall.Stat_t)
 if !ok || raw.Uid != uid { return nil, errors.New("control root owner rejected") }
 d, err := os.Open(root)
 if err != nil { return nil, errors.New("control root unavailable") }
 return d, nil
}

func ownedRegular(path string, flags int, uid uint32, create bool) (*os.File, error) {
 if create { flags |= syscall.O_CREAT }
 fd, err := syscall.Open(path, flags|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0600)
 if err != nil { return nil, err }
 f := os.NewFile(uintptr(fd), path)
 st, err := f.Stat()
 if err != nil { f.Close(); return nil, errors.New("control file stat failed") }
 raw, ok := st.Sys().(*syscall.Stat_t)
 if !ok || !st.Mode().IsRegular() || st.Mode().Perm() != 0600 || raw.Nlink != 1 || raw.Uid != uid {
  f.Close()
  return nil, errors.New("control file identity rejected")
 }
 return f, nil
}

func acquire(root string, uid uint32) (*os.File, *os.File, error) {
 dir, err := validateRoot(root, uid)
 if err != nil { return nil,nil,err }
 f, err := ownedRegular(filepath.Join(root,lockName),syscall.O_RDWR,uid,true)
 if err != nil { dir.Close(); return nil,nil,errors.New("control lock open rejected") }
 if err = syscall.Flock(int(f.Fd()),syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
  f.Close(); dir.Close(); return nil,nil,errors.New("control owner busy or lock unavailable")
 }
 // A root-only directory prevents untrusted UID-based inode swaps.
 return dir,f,nil
}

func strictParse(data []byte) (*Record,error) {
 if len(data)==0 || len(data)>maxRecordBytes { return nil,errors.New("control record size invalid") }
 d := json.NewDecoder(bytes.NewReader(data))
 token,err:=d.Token()
 if err!=nil || token!=json.Delim('{') { return nil,errors.New("control record must be object") }
 keys := map[string]bool{}
 for d.More() {
  token,err=d.Token()
  key,ok:=token.(string)
  if err!=nil || !ok || keys[key] { return nil,errors.New("duplicate or malformed control key") }
  switch key { case "schema","generation","session_id","operation_id": default: return nil,errors.New("unknown control key") }
  keys[key]=true
  var v json.RawMessage
  if err=d.Decode(&v); err!=nil { return nil,errors.New("malformed control value") }
 }
 if _,err=d.Token();err!=nil { return nil,errors.New("unterminated control object") }
 if len(keys)!=4 { return nil,errors.New("missing control field") }
 if _,err=d.Token();err!=io.EOF { return nil,errors.New("trailing control data") }
 var r Record
 if err=json.Unmarshal(data,&r);err!=nil { return nil,errors.New("invalid control record types") }
 if r.Schema!=schemaV1 || r.Generation<1 || !identifier.MatchString(r.SessionID) ||
    !identifier.MatchString(r.OperationID) { return nil,errors.New("invalid control owner value") }
 return &r,nil
}

func readUnderLock(root string,uid uint32) (*Record,error) {
 f,err:=ownedRegular(filepath.Join(root,ownerName),syscall.O_RDONLY,uid,false)
 if errors.Is(err,os.ErrNotExist) { return nil,nil }
 if err!=nil { return nil,errors.New("control record open rejected") }
 defer f.Close()
 data,err:=io.ReadAll(io.LimitReader(f,maxRecordBytes+1))
 if err!=nil { return nil,errors.New("control record unreadable") }
 return strictParse(data)
}

func writeUnderLock(root string,dir *os.File,r Record) error {
 data,err:=json.Marshal(r)
 if err!=nil || len(data)>maxRecordBytes { return errors.New("control serialization failed") }
 tmp,err:=os.CreateTemp(root,".winebot-owner-write-")
 if err!=nil { return errors.New("control temporary file unavailable") }
 tmpName:=tmp.Name()
 defer os.Remove(tmpName)
 if err=tmp.Chmod(0600);err!=nil { tmp.Close();return errors.New("control temporary identity failed") }
 if _,err=tmp.Write(append(data,'\n'));err!=nil {tmp.Close();return errors.New("control temporary write failed")}
 if err=tmp.Sync();err!=nil {tmp.Close();return errors.New("control temporary durability failed")}
 if err=tmp.Close();err!=nil {return errors.New("control temporary close failed")}
 if err=os.Rename(tmpName,filepath.Join(root,ownerName));err!=nil {return errors.New("control owner atomic rename failed")}
 if err=dir.Sync();err!=nil {return errors.New("control owner directory durability failed")}
 return nil
}

func claim(root string,uid uint32,sessionID string,expected int64,operationID string) (Record,error) {
 var zero Record
 if !identifier.MatchString(sessionID) || !identifier.MatchString(operationID) ||
    expected<0 || expected>=maxGeneration {return zero,errors.New("invalid control claim")}
 dir,lock,err:=acquire(root,uid)
 if err!=nil {return zero,err}
 defer dir.Close();defer lock.Close()
 current,err:=readUnderLock(root,uid)
 if err!=nil {return zero,err}
 if current!=nil && current.OperationID==operationID {
  if current.SessionID==sessionID && current.Generation==expected+1 {
   if err=dir.Sync();err!=nil {return zero,errors.New("idempotent durability barrier failed")}
   return *current,nil
  }
  return zero,errors.New("operation identity reused")
 }
 actual:=int64(0)
 if current!=nil {actual=current.Generation}
 if actual!=expected {return zero,errors.New("stale control generation")}
 next:=Record{Schema:schemaV1,Generation:actual+1,SessionID:sessionID,OperationID:operationID}
 if err=writeUnderLock(root,dir,next);err!=nil {return zero,err}
 return next,nil
}

func view(root string,uid uint32)(*Record,error){
 dir,lock,err:=acquire(root,uid)
 if err!=nil {return nil,err}
 defer dir.Close();defer lock.Close()
 return readUnderLock(root,uid)
}

// CLI is deliberately fixed to the trusted mount. Never pass a writable
// arbitrary guest path through a CLI, env variable or public API.
func main() {
 const trustedRoot="/winebot-control"
 if os.Geteuid()!=0 {fmt.Fprintln(os.Stderr,"CONTROL_OWNER=REJECTED");os.Exit(73)}
 args:=os.Args[1:]
 switch {
 case len(args)==1 && args[0]=="serve":
  // Never mount this root-only socket into Wine guest or FastAPI process.
  if err:=serveControl(trustedRoot,0,0,0);err!=nil {
   fmt.Fprintln(os.Stderr,"CONTROL_OWNER=REJECTED");os.Exit(73)
  }
 case len(args)==1 && args[0]=="read":
  r,err:=view(trustedRoot,0)
  if err!=nil {fmt.Fprintln(os.Stderr,"CONTROL_OWNER=REJECTED");os.Exit(73)}
  if r==nil {fmt.Println("CONTROL_OWNER=EMPTY")}else{fmt.Println("CONTROL_OWNER=EXISTS")}
 case len(args)==4 && args[0]=="claim":
  expected,err:=strconv.ParseInt(args[2],10,64)
  if err!=nil {fmt.Fprintln(os.Stderr,"CONTROL_OWNER=REJECTED");os.Exit(73)}
  if _,err=claim(trustedRoot,0,args[1],expected,args[3]);err!=nil {
   fmt.Fprintln(os.Stderr,"CONTROL_OWNER=REJECTED");os.Exit(73)
  }
  fmt.Println("CONTROL_OWNER=COMMITTED")
 default:
  fmt.Fprintln(os.Stderr,"CONTROL_OWNER=REJECTED");os.Exit(73)
 }
}
