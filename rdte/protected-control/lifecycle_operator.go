//go:build linux

package main

import (
 "encoding/json"
 "errors"
 "io"
 "strconv"
)

// This projection reports durable authority only. It never asserts that
// a workload has terminated, that custody is live, or that restart is safe.
type lifecycleOperatorReceipt struct {
 Schema string `json:"schema"`
 Generation int64 `json:"generation"`
 Scope string `json:"scope"`
 Phase string `json:"phase"`
 DurableStop bool `json:"durable_stop"`
 Termination string `json:"termination"`
 Admission string `json:"admission"`
}

func lifecycleOperatorStatus(root string,uid uint32)(lifecycleOperatorReceipt,error){
 var zero lifecycleOperatorReceipt
 // Independent STOP lock: never wait for the ordinary dispatch lock.
 // Generation-changing transitions take this lock; quarantine may change
 // phase concurrently, but cannot change the bound generation/scope.
 d,l,err:=acquireStop(root,uid)
 if err!=nil{return zero,err}
 defer d.Close();defer l.Close()
 s,err:=lifecycleRead(root,uid)
 if err!=nil{return zero,err}
 stop,err:=readDurableStop(root,uid)
 if err!=nil{return zero,err}
 if stop!=nil && (s.Phase=="IDLE" || s.Generation!=stop.Generation || s.Scope!=stop.Scope){
  return zero,errors.New("inconsistent lifecycle STOP binding")
 }
 admission:="NOT_ADMITTED"
 if s.Phase!="IDLE" || stop!=nil{admission="BLOCKED"}
 return lifecycleOperatorReceipt{"winebot/lifecycle-operator/v1",s.Generation,s.Scope,s.Phase,stop!=nil,"UNKNOWN",admission},nil
}

// Internal command seam: main fixes the trusted root and enforces root UID.
// The caller may not supply paths, a PID, a release proof or a clear command.
func runLifecycleOperator(root string,uid uint32,args []string,out io.Writer)error{
 if len(args)==1 && args[0]=="lifecycle-status"{
  r,err:=lifecycleOperatorStatus(root,uid)
  if err!=nil{return err}
  return json.NewEncoder(out).Encode(r)
 }
 if len(args)==3 && args[0]=="lifecycle-stop"{
  g,err:=strconv.ParseInt(args[1],10,64)
  if err!=nil || g<1 || strconv.FormatInt(g,10)!=args[1] || !identifier.MatchString(args[2]){
   return errors.New("invalid STOP binding")
  }
  if err=requestDurableStop(root,uid,g,args[2]);err!=nil{return err}
  // A durable acknowledgement is not a cancellation or termination receipt.
  return json.NewEncoder(out).Encode(lifecycleOperatorReceipt{
   "winebot/lifecycle-operator/v1",g,args[2],"STOP_REQUESTED",true,"UNKNOWN","BLOCKED",
  })
 }
 return errors.New("invalid lifecycle command")
}
