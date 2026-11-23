// SPDX-License-Identifier: MIT
package main
import ("fmt";"strings";"testing")
func row(kind, addr string, size, pid uint64) string {
    return fmt.Sprintf("{\"schema\":\"wine-introspection-rdte/v0\",\"source\":\"WIN32_API_ENUMERATED\",\"kind\":%q,\"process_id\":%d,\"address_space\":\"windows_process_va\",\"address\":%q,\"size_bytes\":%d,\"object_id\":null,\"generation\":null,\"semantic_type\":null,\"snapshot\":\"best_effort\",\"coverage\":\"partial\"}",
        kind,pid,addr,size)
}
func valid() string {
    return row("module","0x140000000",8192,42)+"\n"+
        row("heap_allocation","0x200040",256,42)+"\n"+
        row("memory_region","0x200000",4096,42)+"\n"
}
func TestValid(t *testing.T) {
    if err:=verify(strings.NewReader(valid())); err!=nil { t.Fatalf("valid: %v",err) }
}
func TestFailClosed(t *testing.T) {
    good:=valid()
    tests:=map[string]string{
        "missing region":row("module","0x140000000",8192,42)+"\n"+row("heap_allocation","0x200040",256,42)+"\n",
        "extra":good+row("module","0x140000000",8192,42)+"\n",
        "kind":strings.Replace(good,"\"kind\":\"module\"","\"kind\":\"heap_allocation\"",1),
        "unknown field":strings.Replace(good,"\"coverage\":\"partial\"","\"coverage\":\"partial\",\"memory\":\"SECRET\"",1),
        "fabricated type":strings.Replace(good,"\"semantic_type\":null","\"semantic_type\":\"Player\"",1),
        "fabricated id":strings.Replace(good,"\"object_id\":null","\"object_id\":\"h1\"",1),
        "fabricated generation":strings.Replace(good,"\"generation\":null","\"generation\":1",1),
        "source lie":strings.Replace(good,"WIN32_API_ENUMERATED","WINE_OWNED",1),
        "host pointer lie":strings.Replace(good,"windows_process_va","wine_server_host_va",1),
        "cross pid":strings.Replace(good,"\"process_id\":42","\"process_id\":43",1),
        "wrong region":strings.Replace(good,"\"address\":\"0x200000\"","\"address\":\"0x500000\"",1),
        "bad address":strings.Replace(good,"\"address\":\"0x200040\"","\"address\":\"oops\"",1),
        "oversized":strings.Repeat("A",5000),
        "empty":"",
    }
    for name,raw:=range tests {
        t.Run(name,func(t *testing.T) {
            if err:=verify(strings.NewReader(raw));err==nil { t.Fatal("accepted invalid record") }
        })
    }
}
