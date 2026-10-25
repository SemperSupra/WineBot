"""Source-only tests; no Windows/Wine runtime or public artifact publication."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from qualification.compare import compare, validate_observation
from qualification.observe_roundtrip import (
    EXPECTED_OUTPUT,
    FIXTURE_BYTES,
    FIXTURE_SHA256,
    SCENARIO_SHA256,
    make_observation,
    main,
    outcome,
    pe_architecture,
    qualify_binary,
)


def synthetic_pe(machine: int = 0x8664) -> bytes:
    binary = bytearray(256)
    binary[:2] = b"MZ"
    binary[0x3C:0x40] = (128).to_bytes(4, "little")
    binary[128:132] = b"PE\x00\x00"
    binary[132:134] = machine.to_bytes(2, "little")
    return bytes(binary)


@pytest.mark.parametrize(
    ("machine", "architecture"),
    [(0x014C, "x86"), (0x8664, "x86_64"), (0xAA64, "arm64")],
)
def test_parse_known_pe_machine(machine: int, architecture: str):
    assert pe_architecture(synthetic_pe(machine)) == architecture


@pytest.mark.parametrize("bad", [b"", b"MZ", b"evil", synthetic_pe(0x7777)])
def test_bad_pe_rejected(bad: bytes):
    with pytest.raises(ValueError):
        pe_architecture(bad)


def test_binary_verification_requires_same_bytes(tmp_path: Path):
    exe = tmp_path / "synthetic.exe"
    exe.write_bytes(synthetic_pe())
    sha = hashlib.sha256(exe.read_bytes()).hexdigest()
    assert qualify_binary(exe, sha) == (sha, "x86_64")
    with pytest.raises(ValueError):
        qualify_binary(exe, "0" * 64)


def test_symlink_binary_rejected(tmp_path: Path):
    exe = tmp_path / "synthetic.exe"
    exe.write_bytes(synthetic_pe())
    link = tmp_path / "alias.exe"
    link.symlink_to(exe)
    with pytest.raises(ValueError):
        qualify_binary(link, hashlib.sha256(exe.read_bytes()).hexdigest())


def test_normalization_windows_crlf_and_linux_lf():
    expected = hashlib.sha256(EXPECTED_OUTPUT).hexdigest()
    assert outcome(0, EXPECTED_OUTPUT, b"") == ("PASS", expected)
    assert outcome(0, EXPECTED_OUTPUT.replace(b"\n", b"\r\n"), b"") == ("PASS", expected)


@pytest.mark.parametrize(
    ("exit_code", "out", "err"),
    [(41, EXPECTED_OUTPUT, b""), (0, b"other", b"")],
)
def test_error_output_cannot_pass(exit_code: int, out: bytes, err: bytes):
    assert outcome(exit_code, out, err) == ("FAIL", None)


def example(lane: str, status: str = "PASS", binary: str = "c" * 64):
    result_digest = hashlib.sha256(EXPECTED_OUTPUT).hexdigest() if status == "PASS" else None
    return make_observation(
        lane=lane,
        run_id="synthetic-run",
        source_head_sha="a" * 40,
        tested_checkout_sha="b" * 40,
        binary_sha256=binary,
        architecture="x86_64",
        status=status,
        observed_sha256=result_digest,
    )


def test_valid_paired_synthetic_results():
    windows, wine = example("windows"), example("wine")
    assert validate_observation(windows) == windows
    assert validate_observation(wine) == wine
    assert compare(windows, wine)["verdict"] == "PASS"


def test_native_window_oracle_required():
    windows, wine = example("windows", "FAIL"), example("wine")
    assert compare(windows, wine)["verdict"] == "UNQUALIFIED"


def test_same_binary_required_even_when_outputs_agree():
    windows, wine = example("windows"), example("wine", binary="d" * 64)
    assert compare(windows, wine)["reason_code"] == "MISMATCHED_INPUT"


def test_wine_executable_failure_classifies_infra_not_compatibility(tmp_path: Path):
    if os.name == "nt":
        pytest.skip("Wine command is qualified only on Linux")
    exe = tmp_path / "synthetic.exe"
    exe.write_bytes(synthetic_pe())
    artifact = tmp_path / "observation.json"
    code = main([
        "--executor", "wine", "--exe", str(exe),
        "--expected-exe-sha256", hashlib.sha256(exe.read_bytes()).hexdigest(),
        "--run-id", "synthetic-run",
        "--source-head-sha", "a" * 40, "--tested-checkout-sha", "b" * 40,
        "--wine-command", "this-wine-does-not-exist",
        "--output", str(artifact),
    ])
    assert code == 3
    data = json.loads(artifact.read_text(encoding="utf-8"))
    assert data["assertions"][0]["outcome"] == "INFRA_ERROR"
    assert data["execution"]["lane"] == "wine"
    assert compare(example("windows", binary=data["inputs"]["executable_sha256"]), data)["verdict"] == "INFRA_ERROR"


def test_native_on_linux_does_not_pretend_to_run_windows(tmp_path: Path):
    if os.name == "nt":
        pytest.skip("native Linux exclusion test")
    exe = tmp_path / "synthetic.exe"
    exe.write_bytes(synthetic_pe())
    output = tmp_path / "obs.json"
    code = main([
        "--executor", "native", "--exe", str(exe),
        "--expected-exe-sha256", hashlib.sha256(exe.read_bytes()).hexdigest(),
        "--run-id", "synthetic-run", "--source-head-sha", "a" * 40,
        "--tested-checkout-sha", "b" * 40, "--output", str(output),
    ])
    assert code == 3
    assert not output.exists()


def test_existing_output_is_never_overwritten(tmp_path: Path):
    exe = tmp_path / "synthetic.exe"
    exe.write_bytes(synthetic_pe())
    output = tmp_path / "obs.json"
    output.write_text("PRESERVE", encoding="utf-8")
    code = main([
        "--executor", "wine", "--exe", str(exe),
        "--expected-exe-sha256", hashlib.sha256(exe.read_bytes()).hexdigest(),
        "--run-id", "synthetic-run", "--source-head-sha", "a" * 40,
        "--tested-checkout-sha", "b" * 40, "--output", str(output),
    ])
    assert code == 3
    assert output.read_text(encoding="utf-8") == "PRESERVE"


def test_source_fixture_matches_observer_bytes_and_expected_marker():
    src = (Path(__file__).resolve().parents[1]
           / "qualification/fixtures/win32-roundtrip-v1.c").read_text()
    assert 'WB-FIXTURE-V1\\nAa0_\\n' in src
    assert 'WB_COMPAT_ROUNDTRIP_V1:PASS\\n' in src
    assert FIXTURE_SHA256 == hashlib.sha256(FIXTURE_BYTES).hexdigest()
    assert SCENARIO_SHA256 == hashlib.sha256(
        json.dumps({
            "id": "win32-roundtrip-v1", "revision": 1, "test_class": "workflow",
            "steps": [
                "create-new", "write-fixed-bytes", "close", "reopen",
                "read", "verify", "delete",
            ],
            "requirements": ["file-roundtrip"],
        }, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()


@pytest.mark.parametrize(
    ("exit_code", "out", "err"),
    [(1, EXPECTED_OUTPUT, b""), (-9, b"", b""), (0, EXPECTED_OUTPUT, b"warning")],
)
def test_loader_or_stderr_ambiguity_is_infra_not_compatibility(
    exit_code: int, out: bytes, err: bytes,
):
    assert outcome(exit_code, out, err) == ("INFRA_ERROR", None)
