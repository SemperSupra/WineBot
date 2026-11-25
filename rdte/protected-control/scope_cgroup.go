//go:build linux

package main

import (
 "errors"
 "io"
 "os"
 "strings"
 "syscall"
)

const cgroup2Magic = 0x63677270

type cgroupIdentity struct {
 Device uint64
 Inode uint64
}

func cgroupID(dir *os.File) (cgroupIdentity,error) {
 var st syscall.Stat_t
 var fs syscall.Statfs_t
 if err:=syscall.Fstat(int(dir.Fd()),&st);err!=nil{return cgroupIdentity{},err}
 if err:=syscall.Fstatfs(int(dir.Fd()),&fs);err!=nil{return cgroupIdentity{},err}
 if fs.Type!=cgroup2Magic || st.Mode&syscall.S_IFMT!=syscall.S_IFDIR || st.Nlink==0{
  return cgroupIdentity{},errors.New("not a live cgroup v2 directory")
 }
 return cgroupIdentity{uint64(st.Dev),st.Ino},nil
}

func parseCgroupPopulated(b []byte) (bool,error) {
 if len(b)==0 || len(b)>4096 || b[len(b)-1]!='\n'{
  return false,errors.New("invalid event record")
 }
 seen:=map[string]bool{}
 populated:=false
 for _,line:=range strings.Split(strings.TrimSuffix(string(b),"\n"),"\n"){
  fields:=strings.Fields(line)
  if len(fields)!=2 || strings.Join(fields," ")!=line || seen[fields[0]]{
   return false,errors.New("malformed event record")
  }
  seen[fields[0]]=true
  switch fields[0]{
  case "populated","frozen":
   if fields[1]!="0" && fields[1]!="1"{return false,errors.New("invalid event value")}
   if fields[0]=="populated"{populated=fields[1]=="1"}
  default:return false,errors.New("unsupported event field")
  }
 }
 if !seen["populated"]{return false,errors.New("missing populated event")}
 return populated,nil
}

// The caller supplies an already admitted, held-open cgroup directory from
// the trusted host namespace. Identity is local to this boot/mount lifetime;
// this is NOT a durable scope ID or a proof that external launch is closed.
func cgroupPopulated(dir *os.File,want cgroupIdentity)(bool,error){
 got,err:=cgroupID(dir)
 if err!=nil || got!=want{return false,errors.New("scope identity rejected")}
 fd,err:=syscall.Openat(int(dir.Fd()),"cgroup.events",syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC,0)
 if err!=nil{return false,err}
 f:=os.NewFile(uintptr(fd),"cgroup.events")
 defer f.Close()
 b,err:=io.ReadAll(io.LimitReader(f,4097))
 if err!=nil{return false,err}
 p,err:=parseCgroupPopulated(b)
 if err!=nil{return false,err}
 got,err=cgroupID(dir)
 if err!=nil || got!=want{return false,errors.New("scope identity changed")}
 return p,nil
}

// Deliberately no path-based or guest-facing kill API. The real-kernel
// test uses this primitive only on its freshly created fixture subtree.
// Production must independently admit the exact non-root scope, close
// launch/migration gates and bind generation before calling it.
func killCgroupFixture(dir *os.File,want cgroupIdentity)error{
 got,err:=cgroupID(dir)
 if err!=nil || got!=want{return errors.New("scope identity rejected")}
 fd,err:=syscall.Openat(int(dir.Fd()),"cgroup.kill",syscall.O_WRONLY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC,0)
 if err!=nil{return err}
 f:=os.NewFile(uintptr(fd),"cgroup.kill")
 defer f.Close()
 n,err:=f.WriteString("1\n")
 if err!=nil{return err}
 if n!=2{return io.ErrShortWrite}
 return nil
}
