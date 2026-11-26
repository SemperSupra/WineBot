// SPDX-License-Identifier: MIT
// Strict synthetic-only verifier for Wine 11.0's existing +heap trace channel.
package heaptrace

import (
	"bufio"
	"errors"
	"io"
	"regexp"
	"strconv"
	"strings"
)

const maxTraceBytes int64 = 8 << 20
const maxTraceLine = 16 << 10

// These format patterns are grounded in Wine 11.0 dlls/ntdll/heap.c
// RtlAllocateHeap and RtlFreeHeap TRACE calls. They are intentionally narrow.
var (
	allocEvent = regexp.MustCompile(`trace:heap:RtlAllocateHeap handle ([0-9a-fA-Fx]+), flags ([0-9a-fA-Fx]+), size ([0-9a-fA-Fx]+), return ([0-9a-fA-Fx]+), status ([0-9a-fA-Fx]+)\.`)
	freeEvent  = regexp.MustCompile(`trace:heap:RtlFreeHeap handle ([0-9a-fA-Fx]+), flags ([0-9a-fA-Fx]+), ptr ([0-9a-fA-Fx]+), return ([01]), status ([0-9a-fA-Fx]+)\.`)
)

func hexNum(v string) (uint64, error) {
	v = strings.TrimPrefix(strings.ToLower(v), "0x")
	if v == "" { return 0,errors.New("invalid_trace_hex") }
	return strconv.ParseUint(v, 16, 64)
}

// VerifySyntheticLifetime proves only that an exact allocation/free sequence for
// one source-known synthetic pointer and size exists in an externally isolated
// Wine 11 trace stream. It does not establish process identity, application
// object type, global allocation history, complete tracing, or no observer effect.
func VerifySyntheticLifetime(r io.Reader, expectedPointer string, expectedSize uint64) error {
	target,err:=hexNum(expectedPointer)
	if err!=nil || target==0 || expectedSize==0 || target>^uint64(0)-expectedSize {
		return errors.New("invalid_synthetic_target")
	}
	limited:=&io.LimitedReader{R:r,N:maxTraceBytes+1}
	scanner:=bufio.NewScanner(limited)
	scanner.Buffer(make([]byte,4096),maxTraceLine)
	seenAlloc:=false
	seenFree:=false
	var targetHeap uint64
	for scanner.Scan() {
		line:=scanner.Text()
		if m:=allocEvent.FindStringSubmatch(line);m!=nil {
			addr,e1:=hexNum(m[4])
			size,e2:=hexNum(m[3])
			if e1!=nil || e2!=nil { return errors.New("bad_allocation_event") }
			if addr!=target {continue}
			status,e3:=hexNum(m[5])
			handle,e4:=hexNum(m[1])
			if e3!=nil || e4!=nil || status!=0 || size!=expectedSize || seenAlloc {
				return errors.New("contradictory_allocation_event")
			}
			seenAlloc=true
			targetHeap=handle
		} else if m:=freeEvent.FindStringSubmatch(line);m!=nil {
			addr,e1:=hexNum(m[3])
			if e1!=nil {return errors.New("bad_free_event")}
			if addr!=target {continue}
			status,e2:=hexNum(m[5])
			handle,e3:=hexNum(m[1])
			if e2!=nil || e3!=nil || !seenAlloc || seenFree ||
				handle!=targetHeap || m[4]!="1" || status!=0 {
				return errors.New("contradictory_free_event")
			}
			seenFree=true
		}
	}
	if scanner.Err()!=nil || limited.N==0 {return errors.New("trace_lost_or_overbudget")}
	if !seenAlloc || !seenFree {return errors.New("incomplete_synthetic_lifetime")}
	return nil
}
