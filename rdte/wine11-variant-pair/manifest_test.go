// SPDX-License-Identifier: MIT
package main

import (
    "fmt"
    "strings"
    "testing"
)

func sha(ch string) string { return "sha256:" + strings.Repeat(ch, 64) }

func validPair() (Build, Build, Session, Session) {
    stock := Build{"winebot/wine11-build/v1","stock","11.0","wine-11.0",sha("a"),sha("b"),sha("c"),"",sha("d"),"baseline"}
    instr := Build{"winebot/wine11-build/v1","instrumented","11.0","wine-11.0",sha("a"),sha("b"),sha("c"),sha("e"),sha("f"),"optional-native"}
    a := Session{"winebot/wine11-session/v1","stock","stock-session",1,sha("1"),"cloned","stock-prefix",sha("2"),"stock-state",true}
    b := Session{"winebot/wine11-session/v1","instrumented","instrumented-session",1,sha("1"),"cloned","instrumented-prefix",sha("2"),"instrumented-state",true}
    return stock,instr,a,b
}

func TestValidSyntheticPair(t *testing.T) {
    s,i,a,b := validPair()
    if err := validatePair(s,i,a,b); err != nil { t.Fatalf("valid synthetic declarations rejected: %v",err) }
}

func TestFailClosedPairMutations(t *testing.T) {
    cases := map[string]func(*Build,*Build,*Session,*Session){
        "unsupported build schema":func(s,i *Build,a,b *Session){s.Schema="winebot/wine11-build/v0"},
        "unsupported session schema":func(s,i *Build,a,b *Session){b.Schema="winebot/wine11-session/v0"},
        "patch in stock":func(s,i *Build,a,b *Session){s.PatchQueueDigest=sha("e")},
        "stock sensor lie":func(s,i *Build,a,b *Session){s.SensorMode="optional-native"},
        "no instrumentation patch":func(s,i *Build,a,b *Session){i.PatchQueueDigest=""},
        "instrumented sensor disabled claim":func(s,i *Build,a,b *Session){i.SensorMode="baseline"},
        "wrong version":func(s,i *Build,a,b *Session){i.WineVersion="9.0"},
        "different source":func(s,i *Build,a,b *Session){i.SourceArchiveDigest=sha("9")},
        "different toolchain":func(s,i *Build,a,b *Session){i.ToolchainDigest=sha("9")},
        "different dependencies":func(s,i *Build,a,b *Session){i.DependenciesDigest=sha("9")},
        "same image digest":func(s,i *Build,a,b *Session){i.ImageDigest=s.ImageDigest},
        "uppercase digest":func(s,i *Build,a,b *Session){i.ImageDigest="SHA256:"+strings.Repeat("A",64)},
        "shared prefix clone":func(s,i *Build,a,b *Session){b.PrefixCloneID=a.PrefixCloneID},
        "shared writable mount":func(s,i *Build,a,b *Session){b.StateMountID=a.StateMountID},
        "shared session id":func(s,i *Build,a,b *Session){b.SessionID=a.SessionID},
        "different fixture":func(s,i *Build,a,b *Session){b.FixtureDigest=sha("3")},
        "different snapshot":func(s,i *Build,a,b *Session){b.SourceSnapshotDigest=sha("3")},
        "missing generation":func(s,i *Build,a,b *Session){b.Generation=0},
        "live prefix":func(s,i *Build,a,b *Session){b.PrefixOrigin="live"},
        "unadmitted prefix":func(s,i *Build,a,b *Session){b.PrefixOrigin=""},
        "missing source checksum":func(s,i *Build,a,b *Session){a.SourceSnapshotDigest=""},
        "shared read-only declaration":func(s,i *Build,a,b *Session){b.Writable=false},
    }
    for name, mutate := range cases {
        t.Run(name,func(t *testing.T){
            s,i,a,b := validPair()
            mutate(&s,&i,&a,&b)
            if err := validatePair(s,i,a,b); err == nil {t.Fatal("unsafe pair admitted")}
        })
    }
}

func TestStrictRecordRejectsAmbiguousEvidence(t *testing.T) {
    cases := []string{
        "",
        "{}",
        `{"variant":"stock","variant":"instrumented"}`,
        `{"variant":"stock","unrecognized_host_path":"/private"}`,
        `{"variant":{"nested":true}}`,
        `{"variant":"stock"} {"variant":"instrumented"}`,
        `[]`,
        strings.Repeat("x",maxRecordBytes+1),
    }
    for n, src := range cases {
        t.Run(fmt.Sprint(n),func(t *testing.T){
            if _, err := parseBuild(strings.NewReader(src)); err == nil {t.Fatal("ambiguous build accepted")}
        })
    }
}

func TestStrictValidCompleteDocuments(t *testing.T) {
    stock := `{"schema":"winebot/wine11-build/v1","variant":"stock","wine_version":"11.0","upstream_tag":"wine-11.0","source_archive_digest":"` + sha("a") + `","toolchain_digest":"` + sha("b") + `","dependencies_digest":"` + sha("c") + `","patch_queue_digest":"","image_digest":"` + sha("d") + `","sensor_mode":"baseline"}`
    // Explicitly build the fixture by interpolation; no external source values.
    parsed, err := parseBuild(strings.NewReader(stock))
    if err != nil || parsed.Variant != "stock" {t.Fatalf("valid stock JSON rejected: %v",err)}
    if err := validateBuild(parsed,"stock"); err != nil {t.Fatalf("valid stock declaration rejected: %v",err)}
}
