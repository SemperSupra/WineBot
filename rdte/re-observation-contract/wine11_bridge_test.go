// SPDX-License-Identifier: MIT
package evidence

import (
    "encoding/json"
    "fmt"
    "strings"
    "testing"
)

func syntheticWine11Row(kind,address string, size,pid uint64) string {
    return fmt.Sprintf(
        "{\"schema\":\"wine-introspection-rdte/v0\",\"source\":\"WIN32_API_ENUMERATED\",\"kind\":%q,\"process_id\":%d,\"address_space\":\"windows_process_va\",\"address\":%q,\"size_bytes\":%d,\"object_id\":null,\"generation\":null,\"semantic_type\":null,\"snapshot\":\"best_effort\",\"coverage\":\"partial\"}",
        kind,pid,address,size,
    )
}
func validWine11Witness() string {
    return syntheticWine11Row("module","0x140000000",8192,42)+"\n"+
        syntheticWine11Row("heap_allocation","0x200040",256,42)+"\n"+
        syntheticWine11Row("memory_region","0x200000",4096,42)+"\n"
}
func TestNormalizeWine11CurrentState(t *testing.T) {
    sha:=strings.Repeat("a",40)
    items,err:=NormalizeWine11CurrentStateWitness([]byte(validWine11Witness()),sha)
    if err!=nil || len(items)!=3 {t.Fatalf("valid synthetic witness rejected: %v",err)}
    if items[1].SizeBytes==nil || *items[1].SizeBytes!=256 ||
        items[1].Trust!="UNVERIFIED" || items[1].SemanticType!=nil ||
        items[1].SourceCommit!=sha {t.Fatal("incorrect normalized provenance or allocation size")}
    for _,item:=range items {
        raw,err:=json.Marshal(item)
        if err!=nil {t.Fatal(err)}
        if _,err:=Validate(raw);err!=nil {t.Fatalf("normalized item refused: %v",err)}
    }
}
func TestWine11NormalizerRefusesUnprovedEvidence(t *testing.T) {
    good:=validWine11Witness()
    tests:=map[string]string{
        "wrong_source":strings.Replace(good,"WIN32_API_ENUMERATED","WINE_OWNED",1),
        "wrong_schema":strings.Replace(good,"wine-introspection-rdte/v0","wine-introspection-rdte/v7",1),
        "invented_type":strings.Replace(good,"\"semantic_type\":null","\"semantic_type\":\"Player\"",1),
        "fabricated_id":strings.Replace(good,"\"object_id\":null","\"object_id\":\"object-1\"",1),
        "wrong_address_domain":strings.Replace(good,"windows_process_va","wine_server_host_va",1),
        "extra_field":strings.Replace(good,"\"snapshot\":\"best_effort\"","\"unknown\":\"sensitive\",\"snapshot\":\"best_effort\"",1),
        "duplicate_kind_key":strings.Replace(good,"\"kind\":\"module\"","\"kind\":\"module\",\"kind\":\"module\"",1),
        "cross_process":strings.Replace(good,"\"process_id\":42","\"process_id\":43",1),
        "disjoint_region":strings.Replace(good,"\"address\":\"0x200000\"","\"address\":\"0x800000\"",1),
        "overflow":strings.Replace(good,"\"address\":\"0x200040\"","\"address\":\"0xfffffffffffffff0\"",1),
        "missing":strings.Join(strings.Split(good,"\n")[:2],"\n"),
        "extra_record":good+syntheticWine11Row("module","0x140000000",8192,42)+"\n",
        "blank":"",
        "oversized":strings.Repeat("a",13000),
    }
    for name,source:=range tests {
        t.Run(name,func(t *testing.T){
            if _,err:=NormalizeWine11CurrentStateWitness([]byte(source),strings.Repeat("a",40));err==nil{
                t.Fatal("invalid synthetic Wine11 witness accepted")
            }
        })
    }
    if _,err:=NormalizeWine11CurrentStateWitness([]byte(good),"unverified");err==nil {
        t.Fatal("unqualified external source accepted")
    }
}
