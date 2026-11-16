#!/usr/bin/env python3
"""Bounded public-source Freeciv *real process* observation, never SMAC parity.

Deliberately independent of private observatory code. Requires an ephemeral
Linux runner with Freeciv and strace installed. Output is a public-safe manifest;
raw strace, server logs and saves remain on ephemeral scratch and are deleted.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

SCHEMA = "freeciv-surrogate-native/v0.1"
REQUIRED_SIGNALS = ("server_started", "loopback_tcp", "memory_maps", "file_syscalls", "save_created", "clean_stop", "no_external_ipv4_connect")


def digest(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def proc_descendant_pids(ppid):
    """Return process IDs belonging to the trace process's child tree."""
    queue = [ppid]
    result = []
    seen = set()
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        children = Path(f"/proc/{current}/task/{current}/children")
        try:
            raw = children.read_text(encoding="ascii")
        except (OSError, ValueError):
            continue
        for child in raw.split():
            try:
                pid = int(child)
            except ValueError:
                continue
            result.append(pid)
            queue.append(pid)
    return result


def safe_proc_snapshot(trace_pid):
    """Counts only. Never export raw addresses, maps, env, fds, or command lines."""
    for pid in proc_descendant_pids(trace_pid):
        try:
            comm = Path(f"/proc/{pid}/comm").read_text().strip()
            if "freeciv" not in comm.lower() and "civserver" not in comm.lower():
                continue
            lines = Path(f"/proc/{pid}/maps").read_text().splitlines()
            status = Path(f"/proc/{pid}/status").read_text()
            rss = re.search(r"^VmRSS:\s*(\d+) kB$", status, re.M)
            return {"observed": True, "map_regions": len(lines), "rss_kib": int(rss.group(1)) if rss else None}
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return {"observed": False, "map_regions": 0, "rss_kib": None}


def loopback_ready(port, deadline=4):
    expiry = time.monotonic() + deadline
    while time.monotonic() < expiry:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=.2):
                return True
        except OSError:
            time.sleep(.1)
    return False


def send(proc, line):
    if proc.poll() is not None or proc.stdin is None:
        return False
    try:
        proc.stdin.write((line + "\n").encode("ascii"))
        proc.stdin.flush()
        return True
    except (BrokenPipeError, OSError, ValueError):
        return False


def trace_classification(folder):
    """Minimal privacy-safe counts; no raw syscalls or file paths retained."""
    counts = {"file_syscalls": 0, "network_syscalls": 0, "process_syscalls": 0}
    unexpected_external = 0
    for p in Path(folder).glob("syscalls.*"):
        text = p.read_text(errors="replace")
        for line in text.splitlines():
            if "connect(" in line and "AF_INET" in line and "inet_addr(" in line:
                m = re.search(r'inet_addr\("([0-9.]+)"\)', line)
                if m and not m.group(1).startswith("127."):
                    unexpected_external += 1
        counts["file_syscalls"] += sum(text.count(x) for x in ("openat(", "statx(", "newfstatat(", "readlink("))
        counts["network_syscalls"] += sum(text.count(x) for x in ("socket(", "bind(", "listen(", "connect(", "accept("))
        counts["process_syscalls"] += sum(text.count(x) for x in ("clone(", "execve(", "fork("))
    counts["non_loopback_ipv4_connects"] = unexpected_external
    return counts


def inspect_saves(folder):
    manifests = []
    for p in sorted(Path(folder).rglob("*")):
        if p.is_file() and "surrogate" in p.name and p.suffix.lower() in (".sav", ".gz", ".bz2", ".xz", ".zst"):
            manifests.append({"bytes": p.stat().st_size, "sha256": digest(p)})
    return manifests


def run_native(scratch, seed, port=5557):
    server = shutil.which("freeciv-server") or ("/usr/games/freeciv-server" if Path("/usr/games/freeciv-server").is_file() else None)
    trace = shutil.which("strace")
    if not server or not trace:
        raise RuntimeError("FREECIV_OR_STRACE_MISSING")
    root = Path(scratch)
    root.mkdir(parents=True, exist_ok=True)
    saves = root / "saves"
    saves.mkdir()
    args = [server, "--bind", "127.0.0.1", "--Announce", "none",
            "--port", str(port), "--saves", str(saves)]
    # The package-installed executable must be real and nonempty.
    binary = Path(server).resolve()
    version = subprocess.check_output([server, "--version"], timeout=6, text=True).strip().splitlines()[:3]
    trace_cmd = [trace, "-ff", "-qq", "-s", "96", "-o", str(root / "syscalls"),
                 "-e", "trace=%file,%network,%process"] + args
    log_path = root / "server.log"
    observed = {"server_started": False, "loopback_tcp": False, "memory_maps": False,
                "file_syscalls": False, "save_created": False, "clean_stop": False,
                "no_external_ipv4_connect": False}
    snapshots = []
    trace_info = {}
    exit_code = None
    started = time.monotonic()
    with log_path.open("wb") as log:
        proc = subprocess.Popen(trace_cmd, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                                cwd=root, start_new_session=True,
                                env={**os.environ, "HOME": str(root), "LANG": "C.UTF-8", "TZ": "UTC"})
        try:
            observed["server_started"] = loopback_ready(port)
            snap = safe_proc_snapshot(proc.pid)
            observed["memory_maps"] = snap["observed"] and snap["map_regions"] > 0
            snapshots.append(snap)
            for cmd in ("set minplayers 0", "set aifill 2", f"set gameseed {seed}",
                        f"set mapseed {seed}", "set timeout 1", "create Caesar",
                        "aitoggle Caesar", "start"):
                if not send(proc, cmd):
                    break
                time.sleep(.06)
            # The AI game runs for bounded time; neither an internet connection nor GUI is required.
            time.sleep(3)
            send(proc, "save surrogate-a")
            time.sleep(1)
            send(proc, "save surrogate-b")
            time.sleep(1)
            send(proc, "quit")
            try:
                exit_code = proc.wait(timeout=9)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    exit_code = proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    exit_code = proc.wait(timeout=3)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=3)
            if proc.stdin:
                proc.stdin.close()
    trace_info = trace_classification(root)
    observed["file_syscalls"] = trace_info["file_syscalls"] > 0
    observed["no_external_ipv4_connect"] = trace_info["non_loopback_ipv4_connects"] == 0
    save_info = inspect_saves(saves)
    observed["save_created"] = any(x["bytes"] >= 128 for x in save_info)
    observed["loopback_tcp"] = observed["server_started"]
    observed["clean_stop"] = exit_code == 0
    return {
        "schema": SCHEMA, "status": "PASS" if all(observed.get(k, False) for k in REQUIRED_SIGNALS) else "FAIL",
        "execution_class": "REAL_OPEN_SOURCE_NATIVE_ELF_NOT_SMAC_ORACLE",
        "source": "https://github.com/freeciv/freeciv",
        "license": "GPL-2.0-or-later",
        "binary_sha256": digest(binary),
        "version": version,
        "seed": seed,
        "loopback_only": observed["no_external_ipv4_connect"],
        "signals": observed,
        "trace_counts": trace_info,
        "memory": snapshots,
        "save_digests": save_info,
        "elapsed_s": round(time.monotonic() - started, 2),
        "exit_code": exit_code,
        "limitations": [
            "No source-matched symbol binding or original-1999 binary parity",
            "No Ghidra/Trace RMI, Wine, UI pixels, or full packet payload capture",
            "Kernel/file/network syscall counts are not semantic game-state proof",
            "No proprietary game/OS files or private observatory source were used",
        ],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", required=True, help="Public-safe JSON result file")
    ap.add_argument("--seed", type=int, choices=(42, 43), default=42)
    args = ap.parse_args(argv)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="freeciv-observatory-") as temp:
        try:
            result = run_native(temp, args.seed)
        except (OSError, RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            result = {"schema": SCHEMA, "status": "ERROR", "error_code": type(exc).__name__,
                      "error_class": str(exc) if isinstance(exc, RuntimeError) else "NATIVE_PROBE_FAILURE",
                      "execution_class": "NOT_QUALIFIED", "seed": args.seed}
        output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        print(json.dumps({"status": result["status"], "signals": result.get("signals", {}),
                          "seed": args.seed, "out": str(output)}, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
