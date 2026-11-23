// SPDX-License-Identifier: MIT
package evidence
import ("encoding/json";"strings";"testing")
func str(s string)*string{return &s}
func sizePtr(n uint64)*uint64{return &n}
func fixture(sensor string) Observation{
    o:=Observation{
        Schema:Schema,Backend:"windows",Sensor:sensor,Kind:"nt_handle",
        Origin:"synthetic_fixture",ProcessID:44,AddressSpace:"none",
        Coverage:"partial",SourceCommit:strings.Repeat("a",40),Trust:"UNVERIFIED",
    }
    if sensor=="traceevent"{o.Kind="etw_transition"}
    if sensor=="win32_api"{o.Backend="wine";o.Kind="heap_allocation";o.AddressSpace="windows_process_va";o.Address=str("0x200040");o.SizeBytes=sizePtr(256)}
    return o
}
func TestSupportedSyntheticSources(t *testing.T){
    for _,src:=range []string{"win32_api","phnt","traceevent"}{
        o:=fixture(src)
        b,_:=json.Marshal(o)
        if _,err:=Validate(b);err!=nil{t.Errorf("%s rejected: %v",src,err)}
    }
}
func TestRejectFabricatedEvidence(t *testing.T){
    base:=fixture("win32_api")
    modifications:=map[string]func(*Observation){
        "private target":func(o *Observation){o.Origin="private_target"},
        "claimed verification":func(o *Observation){o.Trust="VERIFIED"},
        "type inference":func(o *Observation){o.SemanticType=str("Player")},
        "object identity":func(o *Observation){o.ObjectID=str("known")},
        "address domain":func(o *Observation){o.AddressSpace="wine_server_host_va"},
        "lost address":func(o *Observation){o.Address=nil},
        "bad address":func(o *Observation){o.Address=str("0x0")},
        "size missing":func(o *Observation){o.SizeBytes=nil},
        "size zero":func(o *Observation){o.SizeBytes=sizePtr(0)},
        "size overflow":func(o *Observation){o.Address=str("0xfffffffffffffff0");o.SizeBytes=sizePtr(100)},
        "wrong backend":func(o *Observation){o.Backend="other"},
        "empty sha":func(o *Observation){o.SourceCommit=""},
        "wrong coverage":func(o *Observation){o.Coverage="complete"},
        "legacy v0":func(o *Observation){o.Schema="winebot.research.observation/v0"},
        "zero process":func(o *Observation){o.ProcessID=0},
        "wrong kind":func(o *Observation){o.Kind="etw_transition"},
        "bad sensor":func(o *Observation){o.Sensor="static_tool"},
    }
    for name,change:=range modifications{
        t.Run(name,func(t *testing.T){
            o:=base
            change(&o)
            b,_:=json.Marshal(o)
            if _,err:=Validate(b);err==nil{t.Fatal("accepted unproven observation")}
        })
    }
    for name,raw:=range map[string]string{
        "duplicate":`{"schema":"x","schema":"winebot.research.observation/v0"}`,
        "extra":`{"raw_memory":"secret"}`,
        "missing":"{}",
        "trailing":"{}{}",
        "oversize":strings.Repeat("x",5000),
    }{
        t.Run(name,func(t *testing.T){if _,err:=Validate([]byte(raw));err==nil{t.Fatal("accepted malformed input")}})
    }
}
