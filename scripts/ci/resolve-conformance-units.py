#!/usr/bin/env python3
"""Narrow test-manifest conflict resolver for disposable PR123+PR154 bake-off.

Do not generalize to production merges. Only a simultaneous append to the
explicit unit-test manifest is resolvable here; all other conflicts fail closed.
"""
from pathlib import Path
import re
import subprocess
import sys

PATH = "scripts/ci/test.sh"
TEST_LINE = re.compile(r"^  (tests/test_[a-z0-9_]+\.py)(?: \\)?$")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True)


def parse(source: str) -> tuple[str, list[str]]:
    lines = source.splitlines()
    i = next((n for n, line in enumerate(lines) if TEST_LINE.fullmatch(line)), -1)
    if i < 0:
        raise ValueError("unit manifest lacks test entries")
    prefix = "\n".join(lines[:i]) + "\n"
    tests = []
    for line in lines[i:]:
        match = TEST_LINE.fullmatch(line)
        if not match:
            raise ValueError("unexpected content in unit-test list")
        tests.append(match.group(1))
    if len(set(tests)) != len(tests):
        raise ValueError("duplicate unit test")
    return prefix, tests


def main() -> int:
    try:
        conflicts = git("diff", "--name-only", "--diff-filter=U").splitlines()
        if conflicts != [PATH]:
            raise ValueError("unexpected conflict set")
        ours = git("show", ":2:" + PATH)
        theirs = git("show", ":3:" + PATH)
        base = git("show", ":1:" + PATH)
        pre_ours, tests_ours = parse(ours)
        pre_theirs, tests_theirs = parse(theirs)
        pre_base, tests_base = parse(base)
        if pre_ours != pre_theirs or pre_ours != pre_base:
            raise ValueError("non-manifest content diverged")
        if set(tests_base) - set(tests_ours) or set(tests_base) - set(tests_theirs):
            raise ValueError("test removed by a candidate")
        if set(tests_ours) - set(tests_base) != {"tests/test_disposable_layer_contract.py"}:
            raise ValueError("unexpected layered source tests")
        integrated = tests_theirs + [s for s in tests_ours if s not in tests_theirs]
        if set(integrated) != set(tests_ours) | set(tests_theirs):
            raise ValueError("test union lost coverage")
        result = pre_theirs + " \\\n".join("  " + s for s in integrated) + "\n"
        Path(PATH).write_text(result, encoding="utf-8")
        subprocess.check_call(["git", "add", "--", PATH])
        if git("diff", "--name-only", "--diff-filter=U").strip():
            raise ValueError("merge still unmerged")
    except (OSError, ValueError, subprocess.CalledProcessError):
        print("LAYERED_CONFORMANCE_RDTE stage=source_merge_conflict", file=sys.stderr)
        return 1
    print("LAYERED_CONFORMANCE_RDTE stage=unit_test_union_resolved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
