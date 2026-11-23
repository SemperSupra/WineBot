// SPDX-License-Identifier: MIT
// Research observation metadata only, not an execution controller or private critic.
package evidence
import ("bytes";"encoding/json";"errors";"io";"regexp";"strconv")
const Schema="winebot.research.observation/v0"
var hexAddress=regexp.MustCompile("^0x[0-9a-f]{1,16}$")
var commitSHA=regexp.MustCompile("^[0-9a-f]{40}$")
type Observation struct {
    Schema string `json:"schema"`
    Backend string `json:"backend"`
    Sensor string `json:"sensor"`
    Kind string `json:"kind"`
    Origin string `json:"origin"`
    ProcessID uint64 `json:"process_id"`
    AddressSpace string `json:"address_space"`
    Address *string `json:"address"`
    SemanticType *string `json:"semantic_type"`
    ObjectID *string `json:"object_id"`
    Generation *uint64 `json:"generation"`
    Coverage string `json:"coverage"`
    SourceCommit string `json:"source_commit"`
    Trust string `json:"trust"`
}
var fields=map[string]bool{
    "schema":true,"backend":true,"sensor":true,"kind":true,
    "origin":true,"process_id":true,"address_space":true,"address":true,
    "semantic_type":true,"object_id":true,"generation":true,
    "coverage":true,"source_commit":true,"trust":true,
}
func Validate(raw []byte) (Observation,error) {
    var out Observation
    if len(raw)==0 || len(raw)>4096 {return out,errors.New("bad_record_size")}
    dec:=json.NewDecoder(bytes.NewReader(raw))
    first,err:=dec.Token()
    if err!=nil || first!=json.Delim('{'){return out,errors.New("not_object")}
    seen:=map[string]bool{}
    for dec.More(){
        tok,err:=dec.Token()
        if err!=nil{return out,errors.New("bad_key")}
        key,ok:=tok.(string)
        if !ok || !fields[key] || seen[key]{return out,errors.New("bad_or_duplicate_key")}
        seen[key]=true
        var v json.RawMessage
        if err:=dec.Decode(&v);err!=nil{return out,errors.New("bad_value")}
    }
    end,err:=dec.Token()
    if err!=nil || end!=json.Delim('}') || len(seen)!=len(fields){
        return out,errors.New("incomplete_record")
    }
    if tok,err:=dec.Token();err!=io.EOF || tok!=nil{
        return out,errors.New("extra_json")
    }
    if err:=json.Unmarshal(raw,&out);err!=nil{return out,errors.New("bad_type")}
    if out.Schema!=Schema || out.Origin!="synthetic_fixture" ||
        out.Coverage!="partial" || out.Trust!="UNVERIFIED" || out.ProcessID==0 ||
        !commitSHA.MatchString(out.SourceCommit){
        return out,errors.New("invalid_provenance")
    }
    if out.SemanticType!=nil || out.ObjectID!=nil || out.Generation!=nil{
        return out,errors.New("unproven_object_semantics")
    }
    ok:=false
    switch out.Sensor {
    case "win32_api":
        ok=(out.Backend=="wine" || out.Backend=="windows") &&
            (out.Kind=="module" || out.Kind=="heap_allocation" || out.Kind=="memory_region")
    case "phnt":
        ok=out.Backend=="windows" && (out.Kind=="nt_process" || out.Kind=="nt_handle")
    case "traceevent":
        ok=out.Backend=="windows" && out.Kind=="etw_transition"
    }
    if !ok{return out,errors.New("unsupported_provider_kind")}
    if out.Sensor=="win32_api"{
        if out.AddressSpace!="windows_process_va" || out.Address==nil ||
            !hexAddress.MatchString(*out.Address){return out,errors.New("wrong_address_domain")}
        n,err:=strconv.ParseUint((*out.Address)[2:],16,64)
        if err!=nil || n==0{return out,errors.New("bad_address")}
    }else if out.AddressSpace!="none" || out.Address!=nil{
        return out,errors.New("wrong_address_domain")
    }
    return out,nil
}
