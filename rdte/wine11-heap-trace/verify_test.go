// SPDX-License-Identifier: MIT
package heaptrace

import (
	"strings"
	"testing"
)

const allocLine = "0034:trace:heap:RtlAllocateHeap handle 0xabc, flags 0, size 0x100, return 0x200040, status 0.\n"
const freeLine = "0034:trace:heap:RtlFreeHeap handle 0xabc, flags 0, ptr 0x200040, return 1, status 0.\n"

func TestWine11SyntheticLifetime(t *testing.T) {
	trace:="unrelated:WineLoader starts\n"+allocLine+
		"0034:trace:heap:RtlAllocateHeap handle 0xdef, flags 0, size 0x20, return 0x300040, status 0.\n"+
		freeLine
	if err:=VerifySyntheticLifetime(strings.NewReader(trace),"0x200040",256);err!=nil {
		t.Fatal(err)
	}
}

func TestWine11FailClosed(t *testing.T) {
	testCases:=map[string]string{
		"missing_free":allocLine,
		"missing_allocate":freeLine,
		"wrong_order":freeLine+allocLine,
		"duplicate_allocation":allocLine+allocLine+freeLine,
		"duplicate_free":allocLine+freeLine+freeLine,
		"wrong_heap":allocLine+"0034:trace:heap:RtlFreeHeap handle 0xdef, flags 0, ptr 0x200040, return 1, status 0.\n",
		"wrong_status":strings.Replace(allocLine,"status 0.","status 0xc0000017.",1)+freeLine,
		"failed_free":allocLine+strings.Replace(freeLine,"return 1, status 0.","return 0, status 0xc000000d.",1),
		"wrong_size":strings.Replace(allocLine,"size 0x100","size 0x80",1)+freeLine,
		"no_heap_trace":strings.Replace(allocLine,"trace:heap:","trace:other:",1)+freeLine,
		"nonsense":"garbage",
		"overbudget":allocLine+strings.Repeat("A",int(maxTraceBytes))+freeLine,
		"line_too_big":allocLine+strings.Repeat("A",maxTraceLine+1)+"\n"+freeLine,
	}
	for name,data:=range testCases {
		t.Run(name,func(t *testing.T){
			if err:=VerifySyntheticLifetime(strings.NewReader(data),"0x200040",256);err==nil{
				t.Fatal("accepted incomplete or contradictory Wine11 trace")
			}
		})
	}
	if err:=VerifySyntheticLifetime(strings.NewReader(allocLine+freeLine),"invalid",256);err==nil {
		t.Fatal("accepted malformed target")
	}
	if err:=VerifySyntheticLifetime(strings.NewReader(allocLine+freeLine),"0x200040",0);err==nil {
		t.Fatal("accepted missing size")
	}
}
