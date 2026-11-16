#!/usr/bin/env python3
"""Actual Freeciv file-read/write/mapping boundary smoke; public-safe evidence only."""
import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import io_boundary
import probe

SCHEMA = "freeciv-io-native/v0.1"


def run(seed, scratch):
    server = shutil.which("freeciv-server") or "/usr/games/freeciv-server"
    tracer = shutil.which("strace")
    if not tracer or not Path(server).is_file():
        raise RuntimeError("NATIVE_DEPENDENCY_MISSING")
    root = Path(scratch)
    saves = root / "saves"
    saves.mkdir()
    port = 5601
    argv = [tracer, "-ff", "-qq", "-yy", "-s", "0", "-o", str(root / "syscalls"),
            "-e", "trace=%file,%network,%process,read,write,pread64,pwrite64,mmap,lseek",
            server, "--bind", "127.0.0.1", "--Announce", "none", "--port", str(port),
            "--saves", str(saves)]
    started = time.monotonic()
    logfile = root / "server.log"
    with logfile.open("wb") as handle:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=handle, stderr=subprocess.STDOUT,
                                cwd=root, start_new_session=True,
                                env={**os.environ, "HOME": str(root), "TZ":"UTC", "LANG":"C.UTF-8"})
        try:
            if not probe.loopback_ready(port, deadline=7):
                raise RuntimeError("SERVER_NOT_READY")
            for cmd in ("set minplayers 0", "set aifill 2", f"set gameseed {seed}",
                        f"set mapseed {seed}", "set timeout 1", "create Caesar",
                        "aitoggle Caesar", "start"):
                if not probe.send(proc, cmd):
                    raise RuntimeError("SERVER_COMMAND_REJECTED")
                time.sleep(.08)
            time.sleep(1.5)
            if not probe.send(proc, "save surrogate-boundary"):
                raise RuntimeError("SAVE_COMMAND_FAILED")
            time.sleep(1)
            if not probe.send(proc, "quit"):
                raise RuntimeError("QUIT_COMMAND_FAILED")
            rc = proc.wait(timeout=12)
            if rc != 0:
                raise RuntimeError("SERVER_EXIT_NONZERO")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=3)
            if proc.stdin:
                proc.stdin.close()
    classified = io_boundary.parse_trace(root)
    saves_seen = probe.inspect_saves(saves)
    files = classified["file_category_counts"]
    signals = {
        "real_game_process_exited_cleanly": True,
        "traced_reads": classified["counters"].get("read_calls",0)>0,
        "traced_writes": classified["counters"].get("write_calls",0)>0,
        "mapped_file_backings": classified["counters"].get("mapping_calls",0)>0,
        "save_file_observed": bool(saves_seen),
        "save_candidate_write_calls": files.get("save_candidate.write_calls",0)>0,
    }
    return {"schema":SCHEMA, "status":"PASS" if all(signals.values()) else "UNQUALIFIED",
            "evidence_class":"REAL_OPEN_SOURCE_FREECIV_IO_BOUNDARY_METADATA_ONLY",
            "binary_sha256": probe.digest(Path(server).resolve()),
            "seed":seed, "signals":signals, "io_summary": classified,
            "elapsed_seconds":round(time.monotonic()-started,2),
            "limitations":["No call stacks, buffer payloads, byte-accurate implicit offsets or decoder labels",
                           "No draw/audio/input surface; this is a headless server",
                           "No private or proprietary game content; external egress not independently firewalled"]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--seed",type=int,choices=(42,43),required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    try:
        with tempfile.TemporaryDirectory(prefix="freeciv-boundary-") as tmp:
            result=run(a.seed,tmp)
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
        result={"schema":SCHEMA,"status":"UNQUALIFIED", "seed":a.seed,
                "evidence_class":"NATIVE_IO_BOUNDARY_NOT_VERIFIED"}
    path=Path(a.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"schema":SCHEMA,"seed":a.seed,"status":result["status"]}))
    return 0 if result["status"]=="PASS" else 1

if __name__=="__main__":
    raise SystemExit(main())
