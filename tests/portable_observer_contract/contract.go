// SPDX-License-Identifier: MIT
// Synthetic, TEST-ONLY portable observer event contract prototype.
// This is not an authorization broker, production source, or WinInspect RPC API.
package observercontract

import (
    "bytes"
    "encoding/json"
    "errors"
    "io"
)

const Contract = "observer.portable.v0"
const RawContract = "winebot.wine.event.v1"
const Source = "win32.setwineventhook"

var (
    ErrInvalid = errors.New("invalid_observation")
    ErrGap = errors.New("observation_gap")
    ErrTerminated = errors.New("stream_terminated")
)

type Frame struct {
    Contract string `json:"contract"`
    Stream string `json:"stream"`
    Source string `json:"source"`
    Sequence int `json:"sequence"`
    Status string `json:"status"`
    Kind string `json:"kind,omitempty"`
}

type Capability struct {
    Contract string `json:"contract"`
    Runtime string `json:"runtime"`
    Source string `json:"source"`
    FixtureScoped bool `json:"fixture_scoped"`
    Features map[string]string `json:"features"`
}

// A capability is a claim made by its runtime, NOT inferred from the JSON schema.
// 'unverified' means a feature must not be used to claim Windows/Wine parity.
// No shared capability is automatically promoted by merely building the adapter.
func UnverifiedCapabilities(runtime string) (Capability, error) {
    if runtime != "windows" && runtime != "wine" {
        return Capability{}, ErrInvalid
    }
    return Capability{
        Contract: Contract, Runtime: runtime, Source: Source, FixtureScoped: true,
        Features: map[string]string{
            "window.create": "unverified", "window.show": "unverified",
            "window.hide": "unverified", "window.destroy": "unverified",
            "window.location": "unverified", "window.focus": "unverified",
            "window.foreground": "unverified",
            "uia.elements": "unverified", "inprocess.hooks": "unverified",
        },
    }, nil
}

type raw struct {
    Schema string `json:"schema"`
    Kind string `json:"kind"`
    Sequence int `json:"sequence"`
}

var canonical = map[string]string{
    "create":"window.created",
    "show":"window.shown",
    "hide":"window.hidden",
    "destroy":"window.destroyed",
    "location":"window.location_changed",
    "focus":"window.focused",
    "foreground":"window.foreground_changed",
}

func decode(line []byte) (raw,error) {
    if len(line)==0 || len(line)>256 {
        return raw{},ErrInvalid
    }
    d:=json.NewDecoder(bytes.NewReader(line))
    d.DisallowUnknownFields()
    var r raw
    if err:=d.Decode(&r); err!=nil { return raw{},ErrInvalid }
    var trailing interface{}
    if err:=d.Decode(&trailing); err!=io.EOF { return raw{},ErrInvalid }
    if r.Schema!=RawContract || r.Sequence<0 || r.Sequence>129 {return raw{},ErrInvalid}
    if _, ok:=canonical[r.Kind]; !ok && r.Kind!="ready" && r.Kind!="overflow" && r.Kind!="unsupported" {
        return raw{},ErrInvalid
    }
    return r,nil
}

// Adapter translates a private fixture-limited producer stream into a portable,
// read-only observation envelope. 'stream' is supplied by a TRUSTED supervisor,
// never extracted from an untrusted producer record. It does not grant authority.
type Adapter struct {
    stream string
    started bool
    terminal bool
    last int
}
func NewAdapter(stream string) (*Adapter,error) {
    if stream=="" || len(stream)>96 { return nil,ErrInvalid }
    return &Adapter{stream:stream},nil
}
func (a *Adapter) envelope(seq int,status,kind string) Frame {
    return Frame{Contract:Contract,Stream:a.stream,Source:Source,Sequence:seq,Status:status,Kind:kind}
}
func (a *Adapter) Consume(line []byte) (Frame,error) {
    if a.terminal { return Frame{},ErrTerminated }
    r,err:=decode(line)
    if err!=nil { a.terminal=true; return Frame{},err }
    if !a.started {
        if r.Sequence!=0 {a.terminal=true; return Frame{},ErrInvalid}
        if r.Kind=="unsupported" {
            a.terminal=true
            return a.envelope(0,"unsupported",""),nil
        }
        if r.Kind!="ready" {a.terminal=true; return Frame{},ErrInvalid}
        a.started=true
        return a.envelope(0,"ready",""),nil
    }
    if r.Kind=="ready" {a.terminal=true; return Frame{},ErrInvalid}
    if r.Sequence!=a.last+1 {
        a.terminal=true
        return a.envelope(r.Sequence,"gap",""),ErrGap
    }
    a.last=r.Sequence
    if r.Kind=="overflow" {
        a.terminal=true
        if r.Sequence!=129 {return Frame{},ErrInvalid}
        return a.envelope(r.Sequence,"overflow",""),nil
    }
    if r.Kind=="unsupported" {
        a.terminal=true
        return a.envelope(r.Sequence,"unsupported",""),nil
    }
    if r.Sequence>128 {
        a.terminal=true
        return Frame{},ErrInvalid
    }
    return a.envelope(r.Sequence,"observed",canonical[r.Kind]),nil
}
