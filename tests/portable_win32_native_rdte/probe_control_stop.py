#!/usr/bin/env python3
"""Synthetic Wine 11 observer terminal-transition oracle; no raw event emission.

The observer remains fixture-scoped and has no live application/WinInspect control.
Only summary PASS/FAIL labels leave this disposable network-disabled container.
"""
import json
import queue
import subprocess
import sys
import threading
import time

def read_lines(pipe, out):
    try:
        for line in iter(pipe.readline, b""):
            out.put(line)
    finally:
        out.put(None)

def terminal_case(observer, command, expected_exit):
    events=queue.Queue(maxsize=132)
    proc=subprocess.Popen(["wine",observer],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL,bufsize=0)
    reader=threading.Thread(target=read_lines,args=(proc.stdout,events),daemon=True)
    reader.start()
    try:
        deadline=time.monotonic()+14
        ready=False
        while time.monotonic()<deadline:
            try:
                line=events.get(timeout=0.3)
            except queue.Empty:
                if proc.poll() is not None:
                    break
                continue
            if line is None:
                break
            if len(line)>256:
                raise ValueError("observer_line_too_large")
            record=json.loads(line.decode("utf-8"))
            if (type(record) is not dict or set(record)!={"schema","kind","sequence"}
                    or record["schema"]!="winebot.wine.event.v1"
                    or record["kind"]!="ready" or record["sequence"]!=0):
                raise ValueError("invalid_ready")
            ready=True
            break
        if not ready:
            raise ValueError("observer_never_ready")
        if command:
            proc.stdin.write(command)
            proc.stdin.flush()
        proc.stdin.close()
        status=proc.wait(timeout=15)
        reader.join(timeout=2)
        if status!=expected_exit:
            raise ValueError("unexpected_terminal_code")
    finally:
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            pass
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.close()
        if proc.stdout:
            proc.stdout.close()

def main():
    if len(sys.argv)!=2:
        raise ValueError("expected_one_observer")
    observer=sys.argv[1]
    for label,command,rc in (("invalid_control",b"X",4),
                             ("pipe_eof",b"",4),
                             ("cooperative_Q",b"Q",0)):
        terminal_case(observer,command,rc)
        print("PASS: wine11_"+label+"_terminal_classified")
    print("PASS: wine11_observer_restarted_after_negative_termination")

if __name__=="__main__":
    try:
        main()
    except (ValueError,OSError,subprocess.SubprocessError,json.JSONDecodeError,UnicodeError):
        print("FAIL: observer_terminal_oracle",file=sys.stderr)
        sys.exit(1)
