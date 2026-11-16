#!/usr/bin/env python3
"""Read-only native Freeciv PC -> ephemeral Ghidra function interval correlation.

Only bounded counts/typed evidence may leave disposable public runner. No raw
addresses, function labels, paths, process memory or game saves are published.
"""
from __future__ import annotations

import argparse
import bisect
import ctypes
import json
import os
import platform
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import elf_map_probe  # noqa: E402 -- sibling's audited public source, no private dependency

SCHEMA = "freeciv-pc-ghidra-bridge/v0.1"
INTERVAL_SCHEMA = "freeciv-ghidra-pc-intervals/v0.1"
MAX_INTERVAL_FILE = 36 * 1024 * 1024
ELF_SHA256 = "33a15db1dc9a250c7ecf215c3fe6d50c34409301f4bb783914a6b16f3b3e8472"
PTRACE_ATTACH = 16
PTRACE_DETACH = 17
PTRACE_GETREGS = 12
PTRACE_SINGLESTEP = 9


class PCError(ValueError):
    """Non-sensitive, stable rejection code."""


def strict_object(pairs):
    o = {}
    for key, value in pairs:
        if key in o:
            raise PCError("DUPLICATE_WITNESS_KEY")
        o[key] = value
    return o


def load_intervals(path, expected_sha256):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not (0 < path.stat().st_size <= MAX_INTERVAL_FILE):
        raise PCError("GHIDRA_INTERVAL_FILE_INVALID")
    try:
        x = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=strict_object)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PCError("GHIDRA_INTERVAL_JSON_INVALID") from exc
    if not isinstance(x, dict) or set(x) != {"schema", "artifact_sha256", "image_base", "intervals", "function_count"}:
        raise PCError("GHIDRA_INTERVAL_SCHEMA_INVALID")
    if x["schema"] != INTERVAL_SCHEMA or x["artifact_sha256"] != expected_sha256:
        raise PCError("GHIDRA_INTERVAL_IDENTITY_MISMATCH")
    if type(x["image_base"]) is not int or x["image_base"] < 0:
        raise PCError("GHIDRA_IMAGE_BASE_INVALID")
    if type(x["function_count"]) is not int or not (100 <= x["function_count"] <= 200000):
        raise PCError("GHIDRA_FUNCTION_COUNT_INVALID")
    arr = x["intervals"]
    if not isinstance(arr, list) or not (x["function_count"] <= len(arr) <= 2000000):
        raise PCError("GHIDRA_INTERVAL_COUNT_INVALID")
    triples = []
    for y in arr:
        if (not isinstance(y, list) or len(y) != 3 or
                any(type(n) is not int for n in y) or not (0 <= y[0] < y[1] <= 2**63) or
                not (1 <= y[2] <= x["function_count"])):
            raise PCError("GHIDRA_RANGE_INVALID")
        triples.append(tuple(y))
    return sorted(triples)


def classify_elf_pc(pc, bias, ranges, executable_segments):
    """Return exactly one of executable-body / ambiguous / executable-unmapped / outside-image."""
    if type(pc) is not int or type(bias) is not int or pc <= 0 or bias < 0 or pc < bias:
        return "OUTSIDE_IMAGE"
    rva = pc - bias
    in_exec = any(vaddr <= rva < vaddr + filesz and flags & 1
                  for _off, vaddr, filesz, flags in executable_segments)
    if not in_exec:
        return "OUTSIDE_IMAGE"
    # A binary search on sorted starts retains exact tie/overlap behavior;
    # a scan of adjoining intervals is acceptable at this size (< 2m).
    starts = [r[0] for r in ranges]
    right = bisect.bisect_right(starts, rva)
    # The intervals are Ghidra function *bodies*, possibly non-contiguous.
    matches = [r for r in ranges[:right] if r[1] > rva]
    if len(matches) > 1:
        return "AMBIGUOUS_FUNCTION"
    return "FUNCTION_MATCH" if matches else "EXECUTABLE_NOT_IN_FUNCTION"


def derive_verified_load_bias(pid, binary, sha256):
    """Verify device/inode/hash and all maps, then derive one unique ASLR bias."""
    _receipt = elf_map_probe.observe_pid(pid, binary, sha256)
    path = Path(binary)
    kind, segments = elf_map_probe.elf_segments(path)
    st = path.stat()
    text = Path(f"/proc/{pid}/maps").read_text(encoding="ascii", errors="replace")
    rows = elf_map_probe.map_rows(text, (os.major(st.st_dev), os.minor(st.st_dev)), st.st_ino)
    page = os.sysconf("SC_PAGE_SIZE")
    votes = {}
    for idx, (start, _end, offset, _perm) in enumerate(rows):
        for soff, va, size, _flags in segments:
            seg_start = soff & ~(page - 1)
            seg_end = (soff + size + page - 1) & ~(page - 1)
            if seg_start <= offset < seg_end:
                bias = start - (va - soff + offset)
                if bias >= 0 and bias % page == 0 and (kind != 2 or bias == 0):
                    votes.setdefault(bias, set()).add(idx)
    if not votes:
        raise PCError("NO_LOAD_BIAS")
    best = max(map(len, votes.values()))
    winners = [v for v, indexes in votes.items() if len(indexes) == best]
    if len(winners) != 1 or best != len(rows):
        raise PCError("LOAD_BIAS_INCONSISTENT")
    return winners[0], segments


# Linux x86-64 kernel user_regs_struct, used only by a direct parent of this
# disposable workcell's own unprivileged child process.
_REGS_FIELDS = ["r15", "r14", "r13", "r12", "rbp", "rbx", "r11", "r10", "r9", "r8", "rax", "rcx", "rdx", "rsi", "rdi", "orig_rax", "rip", "cs", "eflags", "rsp", "ss", "fs_base", "gs_base", "ds", "es", "fs", "gs"]


class UserRegs(ctypes.Structure):
    _fields_ = [(field, ctypes.c_ulonglong) for field in _REGS_FIELDS]


def sample_pc_once(pid):
    """Parent-only ptrace attach/register read/detach, never mutate target memory."""
    libc = ctypes.CDLL(None, use_errno=True)
    ptrace = libc.ptrace
    ptrace.restype = ctypes.c_long
    if ptrace(PTRACE_ATTACH, pid, None, None) != 0:
        raise PCError("PTRACE_ATTACH_NOT_ADMITTED")
    stopped = False
    try:
        got, status = os.waitpid(pid, 0)
        stopped = got == pid and os.WIFSTOPPED(status)
        if not stopped:
            raise PCError("PTRACE_TARGET_NOT_STOPPED")
        registers = UserRegs()
        if ptrace(PTRACE_GETREGS, pid, None, ctypes.byref(registers)) != 0:
            raise PCError("PTRACE_GETREGS_FAILED")
        if not registers.rip:
            raise PCError("PTRACE_NO_INSTRUCTION_POINTER")
        return registers.rip
    finally:
        # A failed attach is never followed by detach; a successful attach
        # always attempts to resume the child even if register inspection fails.
        if ptrace(PTRACE_DETACH, pid, None, None) != 0 and stopped:
            raise PCError("PTRACE_DETACH_FAILED")



def wait_stopped(pid, seconds=3):
    """Bounded wait for a trace stop, protecting the runner from blocked syscalls."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        got, status = os.waitpid(pid, os.WNOHANG)
        if got == pid:
            if not os.WIFSTOPPED(status):
                raise PCError("TRACE_CHILD_EXIT_OR_SIGNAL")
            return status
        time.sleep(.003)
    # Stop the child before releasing debugger ownership; never leave a hung
    # native workcell accidentally under ptrace control.
    try:
        os.kill(pid, signal.SIGSTOP)
        os.waitpid(pid, 0)
    except (ProcessLookupError, ChildProcessError):
        pass
    raise PCError("PTRACE_STEP_TIMEOUT")


def step_until_function(pid, classifier, wake=None, max_steps=2000):
    """Read-only bounded instruction stepping, then detach and resume target.

    The debugger controls the child's execution timing (not target memory) and
    samples real, executed RIP values. A mapping is only valid if the classifier
    independently checked ELF identity and a unique Ghidra function interval.
    """
    if not (1 <= max_steps <= 5000):
        raise PCError("PTRACE_STEP_BUDGET_INVALID")
    libc = ctypes.CDLL(None, use_errno=True)
    ptrace = libc.ptrace
    ptrace.restype = ctypes.c_long
    if ptrace(PTRACE_ATTACH, pid, None, None) != 0:
        raise PCError("PTRACE_ATTACH_NOT_ADMITTED")
    stopped = False
    counts = {k: 0 for k in ("FUNCTION_MATCH", "AMBIGUOUS_FUNCTION",
                             "EXECUTABLE_NOT_IN_FUNCTION", "OUTSIDE_IMAGE")}
    steps = 0
    try:
        wait_stopped(pid)
        stopped = True
        if wake is not None:
            wake()
        while True:
            regs = UserRegs()
            if ptrace(PTRACE_GETREGS, pid, None, ctypes.byref(regs)) != 0:
                raise PCError("PTRACE_GETREGS_FAILED")
            if not regs.rip:
                raise PCError("PTRACE_NO_INSTRUCTION_POINTER")
            label = classifier(regs.rip)
            if label not in counts:
                raise PCError("INTERNAL_CLASSIFIER_INVALID")
            counts[label] += 1
            if label in ("FUNCTION_MATCH", "AMBIGUOUS_FUNCTION") or steps >= max_steps:
                break
            if ptrace(PTRACE_SINGLESTEP, pid, None, None) != 0:
                raise PCError("PTRACE_SINGLESTEP_FAILED")
            stopped = False
            status = wait_stopped(pid)
            stopped = True
            if os.WSTOPSIG(status) != signal.SIGTRAP:
                raise PCError("PTRACE_UNEXPECTED_SIGNAL")
            steps += 1
    finally:
        if stopped and ptrace(PTRACE_DETACH, pid, None, None) != 0:
            raise PCError("PTRACE_DETACH_FAILED")
    return {"steps_executed": steps, "classifications": counts}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_ready(port, proc, deadline_s=8):
    deadline = time.monotonic() + deadline_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=.2):
                return True
        except OSError:
            time.sleep(.1)
    return False


def native_probe(interval_path, binary= "/usr/games/freeciv-server", rounds=140):
    if platform.machine() != "x86_64" or sys.platform != "linux":
        raise PCError("LINUX_X86_64_REQUIRED")
    if not Path(binary).is_file() or elf_map_probe.file_digest(binary) != ELF_SHA256:
        raise PCError("FREECIV_BINARY_DIGEST_MISMATCH")
    ranges = load_intervals(interval_path, ELF_SHA256)
    port = free_port()
    with tempfile.TemporaryDirectory(prefix="freeciv-pc-") as d:
        root = Path(d)
        # The local server is not announced; the only network use is localhost.
        args = [binary, "--bind", "127.0.0.1", "--Announce", "none", "--port", str(port),
                "--saves", str(root / "saves")]
        (root / "saves").mkdir()
        with (root / "server.log").open("wb") as logs:
            proc = subprocess.Popen(args, cwd=root, stdin=subprocess.PIPE, stdout=logs,
                                    stderr=subprocess.STDOUT, text=True, start_new_session=True,
                                    env={**os.environ, "HOME": str(root), "LANG": "C.UTF-8", "TZ": "UTC"})
            try:
                if not wait_ready(port, proc):
                    raise PCError("FREECIV_SERVER_NOT_READY")
                bias, segments = derive_verified_load_bias(proc.pid, binary, ELF_SHA256)
                commands = ("set minplayers 0", "set aifill 2", "set timeout 1", "hard",
                            "create Caesar", "aitoggle Caesar", "start")
                for cmd in commands:
                    if proc.poll() is not None:
                        raise PCError("FREECIV_EXITED_EARLY")
                    proc.stdin.write(cmd + "\n")
                    proc.stdin.flush()
                    time.sleep(.05)
                counts = {k: 0 for k in ("FUNCTION_MATCH", "AMBIGUOUS_FUNCTION",
                                         "EXECUTABLE_NOT_IN_FUNCTION", "OUTSIDE_IMAGE")}
                sampled = 0
                for _ in range(rounds):
                    if proc.poll() is not None:
                        break
                    try:
                        pc = sample_pc_once(proc.pid)
                    except PCError as exc:
                        if str(exc) == "PTRACE_ATTACH_NOT_ADMITTED":
                            raise
                        # Fail closed for any other debugger or lifecycle fault.
                        raise PCError("PTRACE_SAMPLE_INTERRUPTED") from exc
                    counts[classify_elf_pc(pc, bias, ranges, segments)] += 1
                    sampled += 1
                    time.sleep(.025)
                # The server may be idle in libc poll(): passive samples then
                # provide a truthful OUTSIDE_IMAGE negative. Bounded single-step
                # follows *actual executed instructions* back into executable
                # code, while one input command wakes the server's event loop.
                targeted = None
                if counts["FUNCTION_MATCH"] == 0:
                    def wake_server():
                        proc.stdin.write("save pc-wakeup\n")
                        proc.stdin.flush()
                    targeted = step_until_function(
                        proc.pid, lambda pc: classify_elf_pc(pc, bias, ranges, segments),
                        wake=wake_server, max_steps=2400)
                # Verify exact process file/map identity again after sampling.
                derive_verified_load_bias(proc.pid, binary, ELF_SHA256)
                targeted_counts = targeted["classifications"] if targeted is not None else {}
                real_function_hits = counts["FUNCTION_MATCH"] + targeted_counts.get("FUNCTION_MATCH", 0)
                ambiguous_hits = counts["AMBIGUOUS_FUNCTION"] + targeted_counts.get("AMBIGUOUS_FUNCTION", 0)
                result = {
                    "schema": SCHEMA,
                    "evidence_class": "REAL_FREECIV_PTRACE_GHIDRA_FUNCTION_IF_MATCHED",
                    "artifact_sha256": ELF_SHA256,
                    "ptrace_registers_observed": sampled > 0,
                    "one_verified_load_bias": True,
                    "ghidra_interval_count": len(ranges),
                    "sample_count": sampled,
                    "classification_counts": counts,
                    "targeted_single_step": targeted,
                    "function_pc_correlated": real_function_hits > 0 and ambiguous_hits == 0,
                    "no_raw_addresses_uploaded": True,
                }
                result["status"] = "PASS" if result["function_pc_correlated"] else "UNQUALIFIED"
                return result
            finally:
                if proc.poll() is None:
                    try:
                        proc.stdin.write("quit\n")
                        proc.stdin.flush()
                        proc.wait(timeout=4)
                    except (OSError, subprocess.TimeoutExpired):
                        proc.kill()
                        proc.wait(timeout=3)
                if proc.stdin:
                    proc.stdin.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--intervals", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--rounds", type=int, default=140)
    opts = ap.parse_args(argv)
    dest = Path(opts.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        if not 1 <= opts.rounds <= 240:
            raise PCError("ROUND_BUDGET_INVALID")
        report = native_probe(opts.intervals, rounds=opts.rounds)
    except (PCError, OSError, ValueError) as exc:
        report = {"schema": SCHEMA, "status": "UNQUALIFIED", "evidence_class": "RUNTIME_PC_NOT_QUALIFIED",
                  "error_code": str(exc) if isinstance(exc, PCError) else "NATIVE_RUNTIME_FAILURE"}
    dest.write_text(json.dumps(report, sort_keys=True) + "\n")
    print(json.dumps({"schema": SCHEMA, "status": report["status"], "error_code": report.get("error_code")}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
