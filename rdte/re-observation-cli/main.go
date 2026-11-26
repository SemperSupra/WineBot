// SPDX-License-Identifier: MIT
// Read-only local CLI for the synthetic Wine 11 evidence join.
package main

import (
 "encoding/json"
 "flag"
 "fmt"
 "io"
 "os"

 rejoin "../re-lifetime-join"
)

func run(args []string, out io.Writer) int {
 flags := flag.NewFlagSet("winebot-observation", flag.ContinueOnError)
 flags.SetOutput(io.Discard)
 witnessPath := flags.String("witness", "", "local synthetic current-state JSONL")
 tracePath := flags.String("trace", "", "local filtered synthetic heap trace")
 source := flags.String("source-commit", "", "externally asserted source commit")
 if flags.Parse(args) != nil || flags.NArg() != 0 || *witnessPath == "" || *tracePath == "" || *source == "" {
  return 2
 }
 // Refuse nonregular inputs before opening. This CLI is for trusted local
 // fixture directories, not hostile paths or a remotely exposed service.
 open := func(path string) (*os.File, error) {
  st, err := os.Lstat(path)
  if err != nil || !st.Mode().IsRegular() {
   return nil, fmt.Errorf("invalid local fixture")
  }
  return os.Open(path)
 }
 witness, err := open(*witnessPath)
 if err != nil { return 1 }
 defer witness.Close()
 trace, err := open(*tracePath)
 if err != nil { return 1 }
 defer trace.Close()
 receipt, err := rejoin.VerifySyntheticLifetimeJoin(witness, trace, *source)
 if err != nil { return 1 }
 if json.NewEncoder(out).Encode(receipt) != nil { return 1 }
 return 0
}

func main() {
 code := run(os.Args[1:], os.Stdout)
 if code != 0 { fmt.Fprintln(os.Stderr, "WINEBOT_OBSERVATION=REFUSED") }
 os.Exit(code)
}
