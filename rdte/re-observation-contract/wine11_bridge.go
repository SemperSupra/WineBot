// SPDX-License-Identifier: MIT
// Strict bridge from source-Wine11's original synthetic current-state witness.
package evidence

import (
    "bytes"
    "encoding/json"
    "errors"
    "io"
    "strconv"
)

const wine11WitnessSchema = "wine-introspection-rdte/v0"
type wine11Witness struct {
    Schema string `json:"schema"`
    Source string `json:"source"`
    Kind string `json:"kind"`
    ProcessID uint64 `json:"process_id"`
    AddressSpace string `json:"address_space"`
    Address string `json:"address"`
    SizeBytes uint64 `json:"size_bytes"`
    ObjectID *string `json:"object_id"`
    Generation *uint64 `json:"generation"`
    SemanticType *string `json:"semantic_type"`
    Snapshot string `json:"snapshot"`
    Coverage string `json:"coverage"`
}

var wine11WitnessKeys = map[string]bool{
    "schema":true,"source":true,"kind":true,"process_id":true,
    "address_space":true,"address":true,"size_bytes":true,
    "object_id":true,"generation":true,"semantic_type":true,
    "snapshot":true,"coverage":true,
}

func decodeWine11Witness(data []byte) (wine11Witness,error) {
    var out wine11Witness
    if len(data)==0 || len(data)>4096 {return out,errors.New("bad_wine11_record_size")}
    dec:=json.NewDecoder(bytes.NewReader(data))
    start,err:=dec.Token()
    if err!=nil || start!=json.Delim('{') {return out,errors.New("bad_wine11_object")}
    seen:=map[string]bool{}
    for dec.More() {
        token,err:=dec.Token()
        if err!=nil {return out,errors.New("bad_wine11_key")}
        key,ok:=token.(string)
        if !ok || !wine11WitnessKeys[key] || seen[key] {
            return out,errors.New("bad_or_duplicate_wine11_key")
        }
        seen[key]=true
        var raw json.RawMessage
        if err:=dec.Decode(&raw);err!=nil{return out,errors.New("bad_wine11_value")}
    }
    end,err:=dec.Token()
    if err!=nil || end!=json.Delim('}') || len(seen)!=len(wine11WitnessKeys) {
        return out,errors.New("incomplete_wine11_record")
    }
    if token,err:=dec.Token();err!=io.EOF || token!=nil {
        return out,errors.New("trailing_wine11_json")
    }
    if err:=json.Unmarshal(data,&out);err!=nil{return out,errors.New("wine11_field_type")}
    if out.Schema!=wine11WitnessSchema || out.Source!="WIN32_API_ENUMERATED" ||
        out.AddressSpace!="windows_process_va" || out.Snapshot!="best_effort" ||
        out.Coverage!="partial" || out.ProcessID==0 || out.SizeBytes==0 ||
        out.ObjectID!=nil || out.Generation!=nil || out.SemanticType!=nil ||
        !hexAddress.MatchString(out.Address) {
        return out,errors.New("unproved_wine11_record")
    }
    base,err:=strconv.ParseUint(out.Address[2:],16,64)
    if err!=nil || base==0 || base>^uint64(0)-out.SizeBytes{
        return out,errors.New("invalid_wine11_extent")
    }
    return out,nil
}

// NormalizeWine11CurrentStateWitness converts exactly three metadata-only
// synthetic records. The external Git/run SHA must still be verified by the
// owning runner; this function never claims a LIVE or verified source.
func NormalizeWine11CurrentStateWitness(data []byte, expectedCommit string) ([]Observation,error) {
    if !commitSHA.MatchString(expectedCommit) || len(data)==0 || len(data)>12288 {
        return nil,errors.New("invalid_source_or_witness_size")
    }
    raw:=bytes.TrimSuffix(data,[]byte("\n"))
    lines:=bytes.Split(raw,[]byte("\n"))
    if len(lines)!=3 {return nil,errors.New("invalid_record_count")}
    ordered:=[3]string{"module","heap_allocation","memory_region"}
    var items [3]wine11Witness
    records:=make([]Observation,0,3)
    serialized:=make([][]byte,0,3)
    for i,line:=range lines {
        one,err:=decodeWine11Witness(bytes.TrimSuffix(line,[]byte("\r")))
        if err!=nil || one.Kind!=ordered[i] {return nil,errors.New("invalid_record_or_order")}
        if i>0 && one.ProcessID!=items[0].ProcessID {return nil,errors.New("mixed_wine11_pid")}
        items[i]=one
        address:=one.Address
        size:=one.SizeBytes
        value:=Observation{
            Schema:Schema,Backend:"wine",Sensor:"win32_api",
            Kind:one.Kind,Origin:"synthetic_fixture",ProcessID:one.ProcessID,
            AddressSpace:"windows_process_va",Address:&address,SizeBytes:&size,
            Coverage:"partial",SourceCommit:expectedCommit,Trust:"UNVERIFIED",
        }
        encoded,err:=json.Marshal(value)
        if err!=nil{return nil,errors.New("cannot_normalize_wine11")}
        records=append(records,value)
        serialized=append(serialized,encoded)
    }
    module,heap,region:=items[0],items[1],items[2]
    if module.SizeBytes<4096 || heap.SizeBytes<256 || region.SizeBytes<heap.SizeBytes{
        return nil,errors.New("invalid_wine11_sizes")
    }
    heapBase,_:=strconv.ParseUint(heap.Address[2:],16,64)
    regionBase,_:=strconv.ParseUint(region.Address[2:],16,64)
    if heapBase<regionBase || heapBase-regionBase>=region.SizeBytes ||
        heap.SizeBytes>region.SizeBytes-(heapBase-regionBase) {
        return nil,errors.New("wine11_heap_outside_region")
    }
    if err:=ValidateOneSensorBatch(serialized,expectedCommit);err!=nil {
        return nil,errors.New("wine11_normalized_batch_invalid")
    }
    return records,nil
}
