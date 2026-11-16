#!/usr/bin/env python3
"""Public-safe, read-only ELF->live-/proc maps correlation for source-known native surrogate.

This is an ELF segment/load-map identity check, NOT PC sampling, instruction
coverage, Ghidra function attribution, or original-game semantic proof.
No raw addresses, paths, maps, memory, or executable content are emitted.
"""
from __future__ import annotations

import hashlib
import os
import re
import struct
from pathlib import Path

MAX_PROGRAM_HEADERS = 256
MAX_MAP_BYTES = 1 << 20
MAP_PATTERN = re.compile(r"^([0-9a-f]+)-([0-9a-f]+)\s+(\S{4})\s+([0-9a-f]+)\s+([0-9a-f]+):([0-9a-f]+)\s+(\d+)(?:\s|$)")


class CorrelationError(ValueError):
    """Non-sensitive, stable type for fail-closed correlation."""


def file_digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def elf_segments(path):
    """Extract bounded little-endian ELF64 PT_LOAD file-backed segments."""
    with open(path, "rb") as fh:
        hdr = fh.read(64)
        if len(hdr) < 64 or hdr[:4] != b"\x7fELF" or hdr[4] != 2 or hdr[5] != 1:
            raise CorrelationError("ELF64_LITTLE_ENDIAN_REQUIRED")
        fields = struct.unpack_from("<HHIQQQIHHHHHH", hdr, 16)
        kind, phoff, phsize, phcount = fields[0], fields[4], fields[8], fields[9]
        if kind not in (2, 3) or phsize != 56 or not (1 <= phcount <= MAX_PROGRAM_HEADERS):
            raise CorrelationError("ELF_PROGRAM_HEADERS_INVALID")
        limit = os.fstat(fh.fileno()).st_size
        if phoff > limit or phcount * phsize > limit - phoff:
            raise CorrelationError("ELF_PROGRAM_HEADERS_OUT_OF_BOUNDS")
        fh.seek(phoff)
        segments = []
        for _ in range(phcount):
            raw = fh.read(phsize)
            if len(raw) != phsize:
                raise CorrelationError("ELF_PROGRAM_HEADERS_TRUNCATED")
            typ, flags, offset, vaddr, _paddr, filesz, memsz, _align = struct.unpack("<IIQQQQQQ", raw)
            if typ != 1:
                continue
            if not filesz or filesz > memsz or offset > limit or filesz > limit - offset:
                if filesz:
                    raise CorrelationError("ELF_LOAD_SEGMENT_INVALID")
                continue
            segments.append((offset, vaddr, filesz, flags))
    if not segments:
        raise CorrelationError("ELF_FILE_BACKED_LOAD_SEGMENTS_MISSING")
    return kind, segments


def map_rows(text, device, inode):
    """Select only matching file identities; avoid matching on spoofable paths."""
    result = []
    for line in text.splitlines():
        match = MAP_PATTERN.match(line)
        if not match:
            continue
        lo, hi, perm, off, maj, minor, ino = match.groups()
        if int(ino) != inode or (int(maj, 16), int(minor, 16)) != device:
            continue
        low, high = int(lo, 16), int(hi, 16)
        if high <= low or perm[0] != "r":
            continue
        result.append((low, high, int(off, 16), perm))
    return result


def correlate_map_text(text, segments, device, inode, kind, page_size=4096):
    if page_size <= 0 or page_size & (page_size - 1):
        raise CorrelationError("PAGE_SIZE_INVALID")
    rows = map_rows(text, device, inode)
    if not rows:
        raise CorrelationError("NO_EXACT_INODE_DEVICE_EXECUTABLE_MAPPING")
    votes = {}
    for index, (start, end, mapoff, perms) in enumerate(rows):
        for off, vaddr, filesz, _flags in segments:
            seg_start = off & ~(page_size - 1)
            seg_end = (off + filesz + page_size - 1) & ~(page_size - 1)
            if not (seg_start <= mapoff < seg_end):
                continue
            # Linux file VMA: start = load_bias + (p_vaddr-p_offset) + mapoff.
            bias = start - (vaddr - off + mapoff)
            if bias < 0 or bias % page_size or (kind == 2 and bias != 0):
                continue
            votes.setdefault(bias, set()).add(index)
    if not votes:
        raise CorrelationError("NO_CONSISTENT_LOAD_BIAS")
    best = max(len(v) for v in votes.values())
    winners = [bias for bias, support in votes.items() if len(support) == best]
    if len(winners) != 1 or best < 2:
        raise CorrelationError("ELF_LOAD_BIAS_AMBIGUOUS_OR_INSUFFICIENT")
    chosen = winners[0]
    matched = votes[chosen]
    exec_matched = {index for index in matched if "x" in rows[index][3]}
    if not exec_matched:
        raise CorrelationError("NO_EXECUTABLE_PT_LOAD_MATCH")
    # All readable executable-file mappings must cohere with one inferred bias.
    if len(matched) != len(rows):
        raise CorrelationError("ELF_MAPS_INCONSISTENT_WITH_LOAD_BIAS")
    return {"status": "CORRELATED_ELF_LOAD_MAP_NOT_PC", "matching_file_maps": len(rows),
            "matched_load_maps": len(matched), "executable_maps": len(exec_matched),
            "file_backed_segments": len(segments), "one_load_bias": True,
            "raw_addresses_exported": False, "pc_observed": False}


def observe_pid(pid, executable, expected_sha256):
    """Read-only PID and exact ELF identity, fail closed without publicizing paths."""
    executable = Path(executable)
    st = executable.stat()
    pst = Path(f"/proc/{int(pid)}/exe").stat()
    if (st.st_dev, st.st_ino) != (pst.st_dev, pst.st_ino):
        raise CorrelationError("PROCESS_EXECUTABLE_IDENTITY_MISMATCH")
    if file_digest(executable) != expected_sha256:
        raise CorrelationError("EXECUTABLE_SHA256_MISMATCH")
    kind, segments = elf_segments(executable)
    map_path = Path(f"/proc/{int(pid)}/maps")
    with map_path.open("rb") as fh:
        data = fh.read(MAX_MAP_BYTES + 1)
    if len(data) > MAX_MAP_BYTES:
        raise CorrelationError("PROC_MAPS_CAPACITY_EXCEEDED")
    return correlate_map_text(data.decode("ascii", errors="replace"), segments,
                              (os.major(st.st_dev), os.minor(st.st_dev)), st.st_ino,
                              kind, os.sysconf("SC_PAGE_SIZE"))
