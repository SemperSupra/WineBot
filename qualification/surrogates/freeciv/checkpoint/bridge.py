#!/usr/bin/env python3
"""Isolated direct-child external breakpoints with scoped state checkpoints.

Linux x86_64 only. This is deliberately NOT a general-purpose memory patch API.
The only executable accepted is the fixed, source-built fixture, with SHA256
checked before launch and against /proc/PID/exe after the first trace stop.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

SCHEMA = "reversing-public-breakpoint-checkpoint/v0.1"
TRACEME = 0
PEEKTEXT = 1
PEEKDATA = 2
POKETEXT = 4
CONT = 7
GETREGS = 12
SETREGS = 13
WORD_BYTES = ctypes.sizeof(ctypes.c_long)
MAX_WALL_S = 12.0
SYMBOLS = ("apply_action", "observe_after", "controlled_state")


class WitnessError(RuntimeError):
    pass


class UserRegs(ctypes.Structure):
    _fields_ = [(k, ctypes.c_ulonglong) for k in (
        "r15", "r14", "r13", "r12", "rbp", "rbx", "r11", "r10", "r9", "r8", "rax",
        "rcx", "rdx", "rsi", "rdi", "orig_rax", "rip", "cs", "eflags", "rsp", "ss",
        "fs_base", "gs_base", "ds", "es", "fs", "gs")]


LIBC = ctypes.CDLL(None, use_errno=True)
LIBC.ptrace.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
LIBC.ptrace.restype = ctypes.c_long


def ptrace(cmd, pid, addr=0, data=0):
    ctypes.set_errno(0)
    val = LIBC.ptrace(cmd, pid, ctypes.c_void_p(addr), ctypes.c_void_p(data))
    err = ctypes.get_errno()
    if val == -1 and err:
        raise WitnessError("PTRACE_OPERATION_FAILED")
    return val


def digest(path):
    with Path(path).open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def symbols(binary):
    out = subprocess.run(["nm", "-n", "--defined-only", str(binary)], check=True,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=4).stdout
    matched = {}
    for line in out.splitlines():
        m = re.fullmatch(r"([0-9a-fA-F]+)\s+([A-Za-z])\s+(\S+)", line)
        if not m or m.group(3) not in SYMBOLS:
            continue
        name = m.group(3)
        if name in matched or m.group(2) not in ("T", "D"):
            raise WitnessError("AMBIGUOUS_FIXTURE_SYMBOL")
        matched[name] = int(m.group(1), 16)
    if set(matched) != set(SYMBOLS):
        raise WitnessError("MISSING_FIXTURE_SYMBOL")
    return matched


def wait_child(pid, deadline):
    while time.monotonic() < deadline:
        got, status = os.waitpid(pid, os.WNOHANG)
        if got == pid:
            return status
        time.sleep(0.005)
    raise WitnessError("CHILD_TIMEOUT")


def require_stop(status, signum):
    if not os.WIFSTOPPED(status) or os.WSTOPSIG(status) != signum:
        raise WitnessError("UNEXPECTED_TRACE_STOP")


def word(pid, addr):
    return ptrace(PEEKTEXT, pid, addr) & ((1 << (WORD_BYTES * 8)) - 1)


def peek_state(pid, addr):
    return ptrace(PEEKDATA, pid, addr) & ((1 << (WORD_BYTES * 8)) - 1)


def getregs(pid):
    reg = UserRegs()
    ptrace(GETREGS, pid, 0, ctypes.addressof(reg))
    return reg


def putregs(pid, reg):
    ptrace(SETREGS, pid, 0, ctypes.addressof(reg))


def run(binary, expected_sha):
    if platform.system() != "Linux" or platform.machine() != "x86_64" or WORD_BYTES != 8:
        raise WitnessError("LINUX_X86_64_REQUIRED")
    user_path = Path(binary)
    if user_path.is_symlink():
        raise WitnessError("INVALID_SOURCE_IDENTITY")
    binary = user_path.resolve()
    if not binary.is_file() or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise WitnessError("INVALID_SOURCE_IDENTITY")
    if digest(binary) != expected_sha:
        raise WitnessError("BINARY_DIGEST_MISMATCH")
    with binary.open("rb") as header_fh:
        header = header_fh.read(20)
    if (len(header) != 20 or header[:6] != b"\x7fELF\x02\x01" or
            int.from_bytes(header[16:18], "little") != 2 or
            int.from_bytes(header[18:20], "little") != 62):
        raise WitnessError("NON_PIE_X86_64_ELF_REQUIRED")
    sym = symbols(binary)
    if sym["apply_action"] == sym["observe_after"] or not sym["controlled_state"]:
        raise WitnessError("INVALID_SYMBOL_MAP")
    # Only a direct child created for this disposable experiment may be traced.
    child = subprocess.Popen([str(binary)], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    deadline = time.monotonic() + MAX_WALL_S
    active = False
    restored = 0
    data = []
    old_words = {}
    try:
        require_stop(wait_child(child.pid, deadline), signal.SIGSTOP)
        active = True
        if digest(f"/proc/{child.pid}/exe") != expected_sha:
            raise WitnessError("LIVE_EXECUTABLE_CHANGED")
        # e_type=ET_EXEC has already been validated. For PIE experiments,
        # derive the load bias independently before using symbol addresses.
        if peek_state(child.pid, sym["controlled_state"]) != 42:
            raise WitnessError("INITIAL_CHECKPOINT_MISMATCH")
        for name in SYMBOLS[:2]:
            addr = sym[name]
            orig = word(child.pid, addr)
            if orig & 0xFF == 0xCC:
                raise WitnessError("PREEXISTING_BREAKPOINT")
            old_words[addr] = orig
            ptrace(POKETEXT, child.pid, addr, (orig & ~0xFF) | 0xCC)
        ptrace(CONT, child.pid)
        for expected_name, expected_value in (("apply_action", 42), ("observe_after", 43)):
            require_stop(wait_child(child.pid, deadline), signal.SIGTRAP)
            regs = getregs(child.pid)
            addr = sym[expected_name]
            if regs.rip - 1 != addr:
                raise WitnessError("BREAKPOINT_LOCATION_MISMATCH")
            state = peek_state(child.pid, sym["controlled_state"])
            if state != expected_value:
                raise WitnessError("CHECKPOINT_STATE_MISMATCH")
            data.append(hashlib.sha256(state.to_bytes(8, "little")).hexdigest())
            # Undo INT3, rewind RIP to execute the original instruction.
            ptrace(POKETEXT, child.pid, addr, old_words[addr])
            regs.rip = addr
            putregs(child.pid, regs)
            if word(child.pid, addr) != old_words[addr]:
                raise WitnessError("BREAKPOINT_RESTORE_FAILED")
            restored += 1
            ptrace(CONT, child.pid)
        status = wait_child(child.pid, deadline)
        active = False
        if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
            raise WitnessError("CHILD_TERMINATION_FAILED")
        return {
            "schema": SCHEMA, "status": "PASS", "evidence_class": "SOURCE_KNOWN_NATIVE_CHILD_BREAKPOINTS",
            "binary_sha256": expected_sha, "breakpoint_hits": len(data),
            "checkpoint_digests": data, "breakpoint_original_bytes_restored": restored == 2,
            "state_transition_observed": data[0] != data[1], "child_clean_exit": True,
            "limitations": ["Only source-known fixture and two selected state checkpoints",
                            "Not a complete process/VM checkpoint or runtime game function proof",
                            "INT3 temporarily changes fixture text; debugger perturbs scheduling"],
        }
    finally:
        if active or child.poll() is None:
            # On an unexpected breakpoint/timeout, terminate only the child
            # launched by this workcell, never an arbitrary external PID.
            try:
                child.kill()
            except ProcessLookupError:
                pass
        try:
            child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=2)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--binary", required=True)
    ap.add_argument("--expected-sha", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = run(args.binary, args.expected_sha)
    except (WitnessError, OSError, subprocess.SubprocessError, ValueError) as exc:
        code = str(exc) if isinstance(exc, WitnessError) else "FIXTURE_EXECUTION_ERROR"
        report = {"schema": SCHEMA, "status": "UNQUALIFIED", "error_code": code}
    out.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"schema": SCHEMA, "status": report["status"],
                      "error_code": report.get("error_code")}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
