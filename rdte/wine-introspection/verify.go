// SPDX-License-Identifier: MIT
// Offline verifier for rights-cleared synthetic Win32 current-state observations.
package main

import (
    "bufio"
    "bytes"
    "encoding/json"
    "errors"
    "fmt"
    "io"
    "os"
    "regexp"
    "strconv"
)

var addrPattern = regexp.MustCompile("^0x[0-9a-f]{1,16}$")
var expectedKeys = map[string]bool{
    "schema":true, "source":true, "kind":true, "process_id":true,
    "address_space":true, "address":true, "size_bytes":true,
    "object_id":true, "generation":true, "semantic_type":true,
    "snapshot":true, "coverage":true,
}

type rec struct { kind string; pid, base, size uint64 }

func value(m map[string]json.RawMessage, key string) (string,error) {
    var v string
    if err := json.Unmarshal(m[key], &v); err != nil || v == "" {
        return "", errors.New("bad string")
    }
    return v,nil
}

func decode(line []byte) (rec,error) {
    var out rec
    var m map[string]json.RawMessage
    if len(line)>4096 { return out,errors.New("oversized JSON record") }
    if !json.Valid(line) {
        if bytes.HasPrefix(line,[]byte("{\"schema\":")) {
            return out,errors.New("malformed schema serialization")
        }
        return out,errors.New("non-schema output contamination")
    }
    if err:=json.Unmarshal(line,&m); err!=nil || len(m)!=len(expectedKeys) {
        return out,errors.New("missing or added fields")
    }
    for k:=range m { if !expectedKeys[k] { return out,errors.New("unknown field") } }
    for _,k:=range []string{"object_id","generation","semantic_type"} {
        if !bytes.Equal(bytes.TrimSpace(m[k]),[]byte("null")) {
            return out,errors.New("unsupported semantic claim")
        }
    }
    required:=map[string]string{
        "schema":"wine-introspection-rdte/v0",
        "source":"WIN32_API_ENUMERATED",
        "address_space":"windows_process_va",
        "snapshot":"best_effort",
        "coverage":"partial",
    }
    for k,want:=range required {
        got,err:=value(m,k)
        if err!=nil || got!=want { return out,errors.New("bad provenance") }
    }
    kind,err:=value(m,"kind")
    if err!=nil || (kind!="module" && kind!="heap_allocation" && kind!="memory_region") {
        return out,errors.New("bad kind")
    }
    out.kind=kind
    if err:=json.Unmarshal(m["process_id"],&out.pid); err!=nil || out.pid==0 {
        return out,errors.New("bad process")
    }
    if err:=json.Unmarshal(m["size_bytes"],&out.size); err!=nil || out.size==0 {
        return out,errors.New("bad size")
    }
    address,err:=value(m,"address")
    if err!=nil || !addrPattern.MatchString(address) { return out,errors.New("bad address") }
    out.base,err=strconv.ParseUint(address[2:],16,64)
    if err!=nil || out.base==0 || out.base>^uint64(0)-out.size {
        return out,errors.New("address overflow")
    }
    return out,nil
}

// This is a best-effort snapshot validator, not a proof of allocation history.
func verify(r io.Reader) error {
    scan:=bufio.NewScanner(io.LimitReader(r,16385))
    scan.Buffer(make([]byte,4096),4096)
    ordered:=[]string{"module","heap_allocation","memory_region"}
    var all []rec
    for scan.Scan() {
        if len(all)==3 { return errors.New("extra record") }
        one,err:=decode(scan.Bytes())
        if err!=nil { return err }
        if one.kind!=ordered[len(all)] { return errors.New("order") }
        if len(all)>0 && one.pid!=all[0].pid { return errors.New("mixed processes") }
        all=append(all,one)
    }
    if scan.Err()!=nil || len(all)!=3 { return errors.New("incomplete input") }
    mod,heap,region:=all[0],all[1],all[2]
    if mod.size<4096 || heap.size<256 || region.size<heap.size {
        return errors.New("size mismatch")
    }
    if heap.base<region.base || heap.base-region.base>=region.size ||
        heap.size>region.size-(heap.base-region.base) {
        return errors.New("heap outside memory region")
    }
    return nil
}

func main() {
    if err:=verify(os.Stdin);err!=nil {
        // Every error is a fixed source-owned classification: no raw input,
        // addresses, paths or data are interpolated into public CI output.
        fmt.Fprintln(os.Stderr,"FAIL: wine_introspection_current_state cause="+err.Error())
        os.Exit(1)
    }
    fmt.Println("PASS: wine_introspection_current_state")
}
