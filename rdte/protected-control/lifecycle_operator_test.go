//go:build linux

package main

import (
 "bytes"
 "encoding/json"
 "os"
 "path/filepath"
 "strconv"
 "testing"
)

func TestLifecycleOperatorIndependentStop(t *testing.T){
 e,root:=emergencyFixture(t)
 g:=e.gate
 var out bytes.Buffer
 invoke:=func(args ...string)lifecycleOperatorReceipt{
  t.Helper();out.Reset()
  if err:=runLifecycleOperator(root,g.uid,args,&out);err!=nil{t.Fatal(err)}
  var r lifecycleOperatorReceipt
  if err:=json.Unmarshal(out.Bytes(),&r);err!=nil{t.Fatal(err)}
  if r.Termination!="UNKNOWN"{t.Fatal("invented termination")}
  return r
 }
 d,l,err:=acquire(root,g.uid)
 if err!=nil{t.Fatal(err)}
 defer func(){d.Close();l.Close()}()
 r:=invoke("lifecycle-status")
 if r.Phase!="RESERVED" || r.DurableStop || r.Admission!="BLOCKED"{t.Fatal(r)}
 args:=[]string{"lifecycle-stop",strconv.FormatInt(g.generation,10),g.scope}
 for i:=0;i<2;i++{
  r=invoke(args...)
  if r.Phase!="STOP_REQUESTED" || !r.DurableStop || r.Admission!="BLOCKED"{t.Fatal(r)}
 }
 r=invoke("lifecycle-status")
 if !r.DurableStop || r.Phase!="RESERVED" || r.Scope!=g.scope{t.Fatal(r)}
}

func TestLifecycleOperatorRejectsUnsafeRequests(t *testing.T){
 e,root:=emergencyFixture(t);g:=e.gate
 for _,args:=range [][]string{
  {"lifecycle-status","/tmp"}, {"lifecycle-stop","0",g.scope},
  {"lifecycle-stop","+1",g.scope},{"lifecycle-stop","1","wrong-scope"},
  {"lifecycle-stop","2",g.scope},{"lifecycle-clear"},{"lifecycle-release"},
 }{
  var out bytes.Buffer
  if err:=runLifecycleOperator(root,g.uid,args,&out);err==nil || out.Len()!=0{t.Fatal("invalid request accepted")}
 }
 if stop,err:=readDurableStop(root,g.uid);err!=nil || stop!=nil{t.Fatal("rejected command mutated STOP",err)}
 if err:=os.WriteFile(filepath.Join(root,durableStopName),[]byte("{"),0600);err!=nil{t.Fatal(err)}
 var out bytes.Buffer
 if err:=runLifecycleOperator(root,g.uid,[]string{"lifecycle-status"},&out);err==nil || out.Len()!=0{t.Fatal("corrupt state represented as valid")}
}
