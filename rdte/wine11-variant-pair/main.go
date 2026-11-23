// SPDX-License-Identifier: MIT
// Offline entrypoint; no network, host inspection, or mutation.
package main

import (
    "fmt"
    "os"
)

func main() {
    if len(os.Args) != 5 {
        fmt.Fprintln(os.Stderr, "FAIL: variant_pair_inputs")
        os.Exit(2)
    }
    files := make([]*os.File, 4)
    for i, name := range os.Args[1:] {
        file, err := os.Open(name)
        if err != nil {
            fmt.Fprintln(os.Stderr, "FAIL: variant_pair_input_unavailable")
            os.Exit(1)
        }
        files[i] = file
        defer file.Close()
    }
    stock, e1 := parseBuild(files[0])
    instrumented, e2 := parseBuild(files[1])
    a, e3 := parseSession(files[2])
    b, e4 := parseSession(files[3])
    if e1 != nil || e2 != nil || e3 != nil || e4 != nil {
        fmt.Fprintln(os.Stderr, "FAIL: variant_pair_schema")
        os.Exit(1)
    }
    if err := validatePair(stock, instrumented, a, b); err != nil {
        fmt.Fprintln(os.Stderr, "FAIL: variant_pair_admission")
        os.Exit(1)
    }
    fmt.Println("PASS: wine11_variant_pair_declaration")
}
