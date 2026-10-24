"""Fail-closed, source-only comparison of native-Windows and Wine observations.

No external runtime calls. Public output has a fixed whitelist of fields and values.
This v0 implementation qualifies deterministic API/workflow assertions only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

OBSERVATION_VERSION = "compat-observation/v0"
REPORT_VERSION = "compat-diff-public/v0"
MAX_BYTES = 1024 * 1024
MAX_ASSERTIONS = 128
HEX256 = re.compile(r"[0-9a-f]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
IDENT = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
LOCALE = re.compile(r"[a-z]{2}-[A-Z]{2}\Z")
SUPPORTED_CLASSES = {"api", "workflow"}
OUTCOMES = {"PASS", "FAIL", "SKIP", "UNQUALIFIED", "INFRA_ERROR"}
VERDICTS = {"PASS", "FAIL", "UNQUALIFIED", "INFRA_ERROR"}
REASONS = {
    "MATCHED", "DIFFERENT_OUTCOME", "DIFFERENT_OUTPUT", "WINDOWS_ORACLE_FAILURE",
    "ASSERTION_UNQUALIFIED", "ASSERTION_INFRA_ERROR", "MISSING_ASSERTION",
    "MISMATCHED_INPUT", "MISMATCHED_PROFILE", "MISSING_CAPABILITY",
    "UNSUPPORTED_CLASS", "NO_ASSERTIONS",
}


class InvalidObservation(ValueError):
    """Untrusted input violates the versioned observation contract."""


def _invalid() -> None:
    raise InvalidObservation("Invalid observation")


def _mapping(value: Any, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        _invalid()
    return value


def _string(value: Any, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        _invalid()
    return value


def _integer(value: Any, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        _invalid()
    return value


def _identifiers(value: Any) -> set[str]:
    if not isinstance(value, list) or len(value) > 64:
        _invalid()
    result = {_string(item, IDENT) for item in value}
    if len(result) != len(value):
        _invalid()
    return result


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _invalid()
        result[key] = value
    return result


def _invalid_constant(_value: str) -> None:
    _invalid()


def load_observation(path: Path) -> dict[str, Any]:
    """Read a bounded JSON document without echoing untrusted contents or file paths."""
    with path.open("rb") as file:
        raw = file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        _invalid()
    try:
        obj = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_invalid_constant,
        )
    except (UnicodeError, ValueError) as exc:
        raise InvalidObservation("Invalid observation") from exc
    return validate_observation(obj)


def validate_observation(obj: Any) -> dict[str, Any]:
    """Validate the complete exact-key v0 envelope (no arbitrary public metadata)."""
    _mapping(obj, {"schema_version", "scenario", "inputs", "execution", "profile", "capabilities", "assertions"})
    if obj["schema_version"] != OBSERVATION_VERSION:
        _invalid()

    scenario = _mapping(obj["scenario"], {"id", "revision", "sha256", "test_class", "required_capabilities"})
    _string(scenario["id"], IDENT)
    _integer(scenario["revision"], 1, 100000)
    _string(scenario["sha256"], HEX256)
    _string(scenario["test_class"], IDENT)
    _identifiers(scenario["required_capabilities"])

    inputs = _mapping(obj["inputs"], {"executable_sha256", "fixture_sha256"})
    for key in inputs:
        _string(inputs[key], HEX256)

    execution = _mapping(obj["execution"], {"lane", "run_id", "source_head_sha", "tested_checkout_sha"})
    if execution["lane"] not in ("windows", "wine"):
        _invalid()
    _string(execution["run_id"], IDENT)
    _string(execution["source_head_sha"], HEX40)
    _string(execution["tested_checkout_sha"], HEX40)

    profile = _mapping(obj["profile"], {"architecture", "locale", "display", "width", "height", "dpi", "renderer"})
    if profile["architecture"] not in ("x86", "x86_64", "arm64"):
        _invalid()
    _string(profile["locale"], LOCALE)
    if profile["display"] not in ("headless", "interactive"):
        _invalid()
    _integer(profile["width"], 1, 16384)
    _integer(profile["height"], 1, 16384)
    _integer(profile["dpi"], 48, 768)
    _string(profile["renderer"], IDENT)

    _identifiers(obj["capabilities"])
    assertions = obj["assertions"]
    if not isinstance(assertions, list) or len(assertions) > MAX_ASSERTIONS:
        _invalid()
    seen: set[str] = set()
    for assertion in assertions:
        _mapping(assertion, {"id", "outcome", "observed_sha256"})
        aid = _string(assertion["id"], IDENT)
        if aid in seen:
            _invalid()
        seen.add(aid)
        if assertion["outcome"] not in OUTCOMES:
            _invalid()
        digest = assertion["observed_sha256"]
        if digest is not None:
            _string(digest, HEX256)
        if assertion["outcome"] == "PASS" and digest is None:
            _invalid()
    return obj


def compare(windows: dict[str, Any], wine: dict[str, Any]) -> dict[str, Any]:
    """Return public-safe summary; incompatible inputs can NEVER yield PASS/FAIL."""
    windows = validate_observation(windows)
    wine = validate_observation(wine)
    if windows["execution"]["lane"] != "windows" or wine["execution"]["lane"] != "wine":
        _invalid()

    counts = {"matched": 0, "different": 0, "unqualified": 0}

    def report(verdict: str, reason: str) -> dict[str, Any]:
        assert verdict in VERDICTS and reason in REASONS
        return {
            "schema_version": REPORT_VERSION,
            "verdict": verdict,
            "reason_code": reason,
            "assertion_counts": counts.copy(),
        }

    for field in ("scenario", "inputs"):
        if windows[field] != wine[field]:
            return report("UNQUALIFIED", "MISMATCHED_INPUT")
    if windows["profile"] != wine["profile"]:
        return report("UNQUALIFIED", "MISMATCHED_PROFILE")
    if windows["scenario"]["test_class"] not in SUPPORTED_CLASSES:
        return report("UNQUALIFIED", "UNSUPPORTED_CLASS")

    required = set(windows["scenario"]["required_capabilities"])
    if not required.issubset(set(windows["capabilities"])) or not required.issubset(set(wine["capabilities"])):
        return report("UNQUALIFIED", "MISSING_CAPABILITY")

    w_assertions = {a["id"]: a for a in windows["assertions"]}
    e_assertions = {a["id"]: a for a in wine["assertions"]}
    if not w_assertions and not e_assertions:
        return report("UNQUALIFIED", "NO_ASSERTIONS")
    if w_assertions.keys() != e_assertions.keys():
        counts["unqualified"] = len(w_assertions.keys() ^ e_assertions.keys())
        return report("UNQUALIFIED", "MISSING_ASSERTION")

    reasons: set[str] = set()
    for assertion_id in sorted(w_assertions):
        baseline, candidate = w_assertions[assertion_id], e_assertions[assertion_id]
        if "INFRA_ERROR" in (baseline["outcome"], candidate["outcome"]):
            return report("INFRA_ERROR", "ASSERTION_INFRA_ERROR")
        if baseline["outcome"] == "FAIL":
            return report("UNQUALIFIED", "WINDOWS_ORACLE_FAILURE")
        if baseline["outcome"] != "PASS" or candidate["outcome"] in ("SKIP", "UNQUALIFIED"):
            counts["unqualified"] += 1
            reasons.add("ASSERTION_UNQUALIFIED")
        elif candidate["outcome"] != "PASS":
            counts["different"] += 1
            reasons.add("DIFFERENT_OUTCOME")
        elif baseline["observed_sha256"] != candidate["observed_sha256"]:
            counts["different"] += 1
            reasons.add("DIFFERENT_OUTPUT")
        else:
            counts["matched"] += 1
    if counts["unqualified"]:
        return report("UNQUALIFIED", "ASSERTION_UNQUALIFIED")
    if counts["different"]:
        return report("FAIL", "DIFFERENT_OUTCOME" if "DIFFERENT_OUTCOME" in reasons else "DIFFERENT_OUTPUT")
    return report("PASS", "MATCHED")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two bounded v0 compatibility observations")
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--wine", required=True, type=Path)
    parser.add_argument("--public-report", required=True, type=Path)
    args = parser.parse_args(argv)
    # Never leave a stale publishable report following an invalid subsequent invocation.
    try:
        args.public_report.unlink(missing_ok=True)
        report = compare(load_observation(args.windows), load_observation(args.wine))
        payload = json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n"
        # Exclusive creation forbids replacing a symlink into another file.
        with args.public_report.open("x", encoding="utf-8") as target:
            target.write(payload)
    except (InvalidObservation, OSError, TypeError, ValueError):
        print("UNQUALIFIED: invalid, missing, or unreadable comparison input/output", file=sys.stderr)
        return 3
    print(f"{report['verdict']}: {report['reason_code']}")
    return {"PASS": 0, "FAIL": 1, "UNQUALIFIED": 2, "INFRA_ERROR": 3}[report["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
