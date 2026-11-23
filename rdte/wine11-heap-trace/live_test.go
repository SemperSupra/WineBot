// SPDX-License-Identifier: MIT
package heaptrace

import (
    "encoding/json"
    "os"
    "strings"
    "testing"
)

func TestPinnedWine11ActualHeapLifetime(t *testing.T) {
    witnessFile:=os.Getenv("WINE11_RDTE_WITNESS")
    traceFile:=os.Getenv("WINE11_RDTE_TRACE")
    if witnessFile=="" && traceFile==""{
        t.Skip("live Wine11 run not provided; offline fixture controls still run")
    }
    if witnessFile=="" || traceFile=="" {t.Fatal("incomplete live evidence inputs")}
    witness,err:=os.ReadFile(witnessFile)
    if err!=nil || len(witness)==0 || len(witness)>12288{t.Fatal("missing or invalid bounded Wine11 witness")}
    lines:=strings.Split(strings.TrimSuffix(string(witness),"\n"),"\n")
    if len(lines)!=3 {t.Fatal("incorrect live observation count")}
    var row struct {
        Schema string `json:"schema"`
        Source string `json:"source"`
        Kind string `json:"kind"`
        Address string `json:"address"`
        SizeBytes uint64 `json:"size_bytes"`
    }
    if err:=json.Unmarshal([]byte(lines[1]),&row);err!=nil{t.Fatal("invalid heap observation")}
    if row.Schema!="wine-introspection-rdte/v0" || row.Source!="WIN32_API_ENUMERATED" ||
        row.Kind!="heap_allocation" || row.SizeBytes<256 {
        t.Fatal("unsupported heap observation provenance")
    }
    trace,err:=os.Open(traceFile)
    if err!=nil{t.Fatal("filtered Wine11 trace unavailable")}
    defer trace.Close()
    if err:=VerifySyntheticLifetime(trace,row.Address,row.SizeBytes);err!=nil{
        // Never print error details or target addresses into public GHA.
        t.Fatal("pinned Wine11 synthetic heap lifetime not observed")
    }
}
