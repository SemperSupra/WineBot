#!/usr/bin/env python3
"""Native Win32 synthetic target correlation falsifier.

No raw window IDs, process IDs, application content, screenshots or control.
Epochs are fixture hints only, NOT attested authority or action tokens.
"""
import json
import queue
import subprocess
import sys
import threading
import time

SCHEMA = "winebot.target.hint.rdte.v0"
KEYS = {"schema","kind","sequence","target_ref","target_epoch"}
KINDS = {"ready","create","show","hide","location","focus","foreground",
         "destroy","gap","overflow"}
REQUIRED = {"show","location","destroy"}

def collect(pipe, out):
    try:
        for line in iter(pipe.readline,b""):
            out.put(line)
    finally:
        out.put(None)

def parse(line):
    if not isinstance(line,bytes) or len(line)>256 or not line:
        raise ValueError("unbounded_event")
    event=json.loads(line.decode("utf-8"))
    if (type(event) is not dict or set(event)!=KEYS or
        event["schema"]!=SCHEMA or event["kind"] not in KINDS or
        type(event["sequence"]) is not int or not 0<=event["sequence"]<=129 or
        type(event["target_epoch"]) is not int or not 0<=event["target_epoch"]<=128 or
        type(event["target_ref"]) is not str or len(event["target_ref"])>48):
        raise ValueError("invalid_schema")
    if event["kind"]=="ready":
        if event["sequence"]!=0 or event["target_ref"] or event["target_epoch"]:
            raise ValueError("invalid_ready")
    elif event["target_epoch"] and event["target_ref"]!=f"fixture-target-{event['target_epoch']}":
        raise ValueError("unexpected_ref")
    return event

def drain(messages, received, seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        try: line=messages.get(timeout=min(0.25,end-time.monotonic()))
        except queue.Empty: continue
        if line is None: break
        received.append(parse(line))

def main():
    if len(sys.argv)==4 and sys.argv[1]=="--wine":
        obs,fixture=sys.argv[2:]
        observe_cmd,fixture_cmd=["wine",obs],["wine",fixture]
        runtime="wine"
    elif len(sys.argv)==3:
        obs,fixture=sys.argv[1:]
        observe_cmd,fixture_cmd=[obs],[fixture]
        runtime="native"
    else:
        raise ValueError("two_executables_required")
    proc=subprocess.Popen(observe_cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL,bufsize=0)
    messages=queue.Queue(maxsize=140)
    threading.Thread(target=collect,args=(proc.stdout,messages),daemon=True).start()
    events=[]
    try:
        end=time.monotonic()+15
        while time.monotonic()<end:
            try: line=messages.get(timeout=0.25)
            except queue.Empty:
                if proc.poll() is not None: break
                continue
            if line is None: break
            event=parse(line)
            if event["kind"]!="ready": raise ValueError("observer_not_ready")
            events.append(event)
            break
        if not events: raise ValueError("missing_ready")
        for rep in range(2):
            result=subprocess.run(fixture_cmd,stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL,timeout=18,check=False)
            if result.returncode!=0: raise ValueError("fixture_failure")
            drain(messages,events,1.25)
            if proc.poll() is not None: raise ValueError("premature_observer_exit")
        proc.stdin.write(b"Q")
        proc.stdin.flush()
        proc.stdin.close()
        proc.wait(timeout=10)
        drain(messages,events,0.4)
        if proc.returncode!=0: raise ValueError("observer_stop_failure")
        if len(events)<7 or len(events)>129: raise ValueError("event_count_out_of_bounds")
        if [e["sequence"] for e in events]!=list(range(len(events))):
            raise ValueError("noncontiguous_event_stream")
        if any(e["kind"] in {"gap","overflow"} for e in events):
            raise ValueError("target_correlation_gap")
        by_epoch={}
        for e in events[1:]:
            if e["target_epoch"]==0: raise ValueError("unscoped_event")
            by_epoch.setdefault(e["target_epoch"],set()).add(e["kind"])
        complete=[epoch for epoch,kinds in by_epoch.items() if REQUIRED<=kinds]
        if len(complete)<2: raise ValueError("two_complete_fixture_epochs_missing")
        if len(set(complete))!=len(complete): raise ValueError("epoch_reuse")
        print("PASS: "+runtime+"_two_sequential_fixture_target_epochs="+str(len(complete)))
        print("PASS: "+runtime+"_scoped_show_location_destroy_and_contiguous_sequence")
        print("PASS: "+runtime+"_no_raw_hwnd_pid_title_or_application_content")
        print("LIMITATION: fixture tokens are not authenticated target identity or actuator authority")
    finally:
        if proc.poll() is None: proc.kill()
        try: proc.wait(timeout=3)
        except subprocess.TimeoutExpired: pass
        if proc.stdin and not proc.stdin.closed: proc.stdin.close()
        if proc.stdout: proc.stdout.close()

if __name__=="__main__":
    try: main()
    except (OSError,ValueError,subprocess.SubprocessError,UnicodeError):
        print("FAIL: native_fixture_target_correlation",file=sys.stderr)
        sys.exit(1)
