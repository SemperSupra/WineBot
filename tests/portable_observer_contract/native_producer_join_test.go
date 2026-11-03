// SPDX-License-Identifier: MIT
// Public-only, same-job integration of ACTUAL native Win32 event-hook output
// and the existing portable read-only WinInspect-like test consumer.
// No private WinInspect source, HWND/PID/title, real user content, or actuator.
package observercontract

import (
    "bufio"
    "encoding/json"
    "os"
    "strings"
    "testing"
)

func TestRealNativeWinEventProducerThroughPortableWinInspectBridge(t *testing.T) {
    path := os.Getenv("WINEBOT_OBSERVER_SAFE_RECEIPT")
    if path == "" {
        t.Skip("requires independently executed native WinEvent fixture in this job")
    }
    input, err := os.Open(path)
    if err != nil { t.Fatal("safe native producer receipt missing") }
    defer input.Close()

    // The stream identity is assigned by this local, trusted fixture
    // supervisor. It is not taken from the untrusted producer record.
    const stream = "native-fixture-source-incarnation"
    adapter, err := NewAdapter(stream)
    if err != nil { t.Fatal(err) }
    relay, err := NewScopedRelay(stream, Source, 1, 128)
    if err != nil { t.Fatal(err) }
    reader := bufio.NewScanner(input)
    reader.Buffer(make([]byte, 512), 1024)
    var bridge *ScopedBridge
    observed := map[string]bool{}
    accepted := 0
    sawReady := false
    for reader.Scan() {
        rawLine := append([]byte(nil), reader.Bytes()...)
        if len(rawLine) == 0 || len(rawLine) > 256 {t.Fatal("unbounded native record")}
        frame, err := adapter.Consume(rawLine)
        if err != nil { t.Fatal("native producer frame rejected by portable adapter: ", err) }
        if err := relay.Accept(frame); err != nil {t.Fatal("native frame rejected by scoped relay: ", err)}
        if !sawReady {
            if frame.Status != "ready" || frame.Sequence != 0 {t.Fatal("missing producer ready")}
            sawReady = true
            bridge, err = relay.NewBridge("wininspect-readonly")
            if err != nil {t.Fatal(err)}
            defer bridge.Close()
            continue
        }
        if frame.Status != "observed" {t.Fatal("terminal or unsupported event in healthy native fixture")}
        observed[frame.Kind] = true
        accepted++
        if accepted > 128 {t.Fatal("native fixture exceeded contract observation cap")}
    }
    if err := reader.Err(); err != nil {t.Fatal("native fixture receipt parse error: ", err)}
    if !sawReady || bridge == nil || accepted == 0 {t.Fatal("native observation was not exercised")}
    for _, required := range []string{"window.shown", "window.location_changed", "window.destroyed"} {
        if !observed[required] {t.Fatalf("native fixture missing actual callback %s", required)}
    }
    hints, err := bridge.Poll(128)
    if err != nil {t.Fatal("native stream not consumable: ", err)}
    if len(hints) != accepted {t.Fatalf("native adapter/consumer count mismatch: %d != %d",len(hints),accepted)}
    for i, hint := range hints {
        if hint.Sequence != i+1 || hint.Scope != "desktop" ||
           hint.Contract != "wininspect.observer.hint.v0" || hint.Reason == "" {
            t.Fatal("wrong read-only native hint chronology or scope")
        }
    }
    wire, err := json.Marshal(hints)
    if err != nil {t.Fatal(err)}
    for _, forbidden := range []string{"hwnd","pid","title","target_ref","target_epoch",
       "action","principal","lease","cursor","reader","class_name"} {
        if strings.Contains(strings.ToLower(string(wire)), forbidden) {
            t.Fatalf("native-to-consumer output leaked prohibited field: %s",forbidden)
        }
    }
    next, err := bridge.Poll(128)
    if err != nil || len(next) != 0 {t.Fatalf("read-only consumer duplicate/replay: %d, %v",len(next),err)}
    t.Logf("PASS native WinEvent -> portable adapter -> WinInspect-like read-only hint, %d callbacks", accepted)
}
