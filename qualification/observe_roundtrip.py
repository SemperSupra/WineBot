"""Generate a source-custody-bound Win32 roundtrip observation, without raw logs.

The same SHA256-pinned PE is executed natively or through Wine. This module
does not claim native Windows proof unless actually run on Windows, and it
does not provide interactive/UI/rendering qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from qualification.compare import validate_observation

MAX_PE_BYTES = 16 * 1024 * 1024
EXPECTED_OUTPUT = b"WB_COMPAT_ROUNDTRIP_V1:PASS\n"
FIXTURE_BYTES = b"WB-FIXTURE-V1\nAa0_\n"
SHA256 = re.compile(r"[a-f0-9]{64}\Z")
SHA40 = re.compile(r"[a-f0-9]{40}\Z")
IDENT = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
MACHINE = {0x014C: "x86", 0x8664: "x86_64", 0xAA64: "arm64"}
SCENARIO = {
    "id": "win32-roundtrip-v1",
    "revision": 1,
    "test_class": "workflow",
    "steps": ["create-new", "write-fixed-bytes", "close", "reopen", "read", "verify", "delete"],
    "requirements": ["file-roundtrip"],
}
SCENARIO_SHA256 = hashlib.sha256(
    json.dumps(SCENARIO, sort_keys=True, separators=(",", ":")).encode("ascii")
).hexdigest()
FIXTURE_SHA256 = hashlib.sha256(FIXTURE_BYTES).hexdigest()


def pe_architecture(binary: bytes) -> str:
    """Reject non-PE or unrecognized machine architectures without launching."""
    if len(binary) < 64 or binary[:2] != b"MZ":
        raise ValueError("Unqualified PE")
    offset = int.from_bytes(binary[0x3C:0x40], "little")
    if offset < 64 or offset + 6 > len(binary) or binary[offset:offset + 4] != b"PE\0\0":
        raise ValueError("Unqualified PE")
    architecture = MACHINE.get(int.from_bytes(binary[offset + 4:offset + 6], "little"))
    if architecture is None:
        raise ValueError("Unqualified PE")
    return architecture


def qualify_binary(path: Path, expected: str) -> tuple[str, str]:
    if not isinstance(expected, str) or SHA256.fullmatch(expected) is None:
        raise ValueError("Invalid expected SHA256")
    # Reject symlinked binary to avoid accidental redirection to another executable.
    if path.is_symlink() or not path.is_file():
        raise ValueError("Unqualified PE")
    if path.stat().st_size > MAX_PE_BYTES:
        raise ValueError("Unqualified PE")
    data = path.read_bytes()
    if len(data) > MAX_PE_BYTES:
        raise ValueError("Unqualified PE")
    sha = hashlib.sha256(data).hexdigest()
    if sha != expected:
        raise ValueError("Executable digest mismatch")
    return sha, pe_architecture(data)


def outcome(returncode: int, stdout: bytes, stderr: bytes) -> tuple[str, str | None]:
    # Never persist or print arbitrary executable output.
    normal = stdout.replace(b"\r\n", b"\n")
    if returncode == 0 and normal == EXPECTED_OUTPUT and not stderr:
        return "PASS", hashlib.sha256(EXPECTED_OUTPUT).hexdigest()
    # Fixture-owned explicit exit statuses indicate an assertion failure. Wine
    # loader problems, signals and ambiguous stderr are infrastructure errors.
    if stderr or returncode not in (0, 41, 42, 43, 44, 45, 46):
        return "INFRA_ERROR", None
    return "FAIL", None


def make_observation(
    lane: str,
    run_id: str,
    source_head_sha: str,
    tested_checkout_sha: str,
    binary_sha256: str,
    architecture: str,
    status: str,
    observed_sha256: str | None,
) -> dict:
    observation = {
        "schema_version": "compat-observation/v0",
        "scenario": {
            "id": SCENARIO["id"],
            "revision": SCENARIO["revision"],
            "sha256": SCENARIO_SHA256,
            "test_class": SCENARIO["test_class"],
            "required_capabilities": ["file-roundtrip"],
        },
        "inputs": {
            "executable_sha256": binary_sha256,
            "fixture_sha256": FIXTURE_SHA256,
        },
        "execution": {
            "lane": lane,
            "run_id": run_id,
            "source_head_sha": source_head_sha,
            "tested_checkout_sha": tested_checkout_sha,
        },
        "profile": {
            "architecture": architecture,
            "locale": "en-US",
            "display": "headless",
            "width": 1,
            "height": 1,
            "dpi": 96,
            "renderer": "none",
        },
        "capabilities": ["file-roundtrip"],
        "assertions": [{
            "id": "file-roundtrip",
            "outcome": status,
            "observed_sha256": observed_sha256,
        }],
    }
    return validate_observation(observation)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthetic, read/write-only Win32 PE qualification")
    parser.add_argument("--executor", choices=("native", "wine"), required=True)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--expected-exe-sha256", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-head-sha", required=True)
    parser.add_argument("--tested-checkout-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wine-command", default="wine")
    args = parser.parse_args(argv)
    try:
        if (IDENT.fullmatch(args.run_id) is None
                or SHA40.fullmatch(args.source_head_sha) is None
                or SHA40.fullmatch(args.tested_checkout_sha) is None):
            raise ValueError("Unqualified receipt identity")
        if args.output.exists() or args.output.is_symlink():
            raise ValueError("Output already exists")
        binary_digest, architecture = qualify_binary(
            args.exe, args.expected_exe_sha256
        )
        if args.executor == "native" and os.name != "nt":
            raise ValueError("Native execution requires actual Windows")
        if args.executor == "wine" and os.name == "nt":
            raise ValueError("Wine execution requires a non-Windows host")
        lane = "windows" if args.executor == "native" else "wine"
        executable = str(args.exe.resolve(strict=True))
        command = [executable] if lane == "windows" else [args.wine_command, executable]
        with tempfile.TemporaryDirectory(prefix="wb-compat-synthetic-") as workdir:
            try:
                result = subprocess.run(
                    command, cwd=workdir, capture_output=True, timeout=30, check=False
                )
                status, digest = outcome(result.returncode, result.stdout, result.stderr)
            except (subprocess.TimeoutExpired, OSError):
                status, digest = "INFRA_ERROR", None
        obs = make_observation(
            lane, args.run_id, args.source_head_sha, args.tested_checkout_sha,
            binary_digest, architecture, status, digest,
        )
        with args.output.open("x", encoding="utf-8") as out:
            json.dump(obs, out, sort_keys=True, separators=(",", ":"))
            out.write("\n")
        return {"PASS": 0, "FAIL": 1, "INFRA_ERROR": 3}[status]
    except (OSError, ValueError, TypeError):
        # Do not include potentially sensitive arguments, stdout, paths or host.
        print("UNQUALIFIED: observation not emitted", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
