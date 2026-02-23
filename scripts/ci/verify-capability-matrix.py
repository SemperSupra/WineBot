#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = REPO_ROOT / "docs" / "test-capability-matrix.md"
ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$")
REF_RE = re.compile(r"`([^`]+)`")


def _normalize_ref(ref: str) -> str:
    return ref.strip()


def _verify_ref_exists(ref: str) -> bool:
    if ref.startswith("http://") or ref.startswith("https://"):
        return True
    path = (REPO_ROOT / ref).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except Exception:
        return False
    return path.exists()


def main() -> int:
    if not MATRIX_PATH.exists():
        print(f"ERROR: matrix file missing: {MATRIX_PATH}")
        return 1

    lines = MATRIX_PATH.read_text(encoding="utf-8").splitlines()
    in_table = False
    errors: list[str] = []
    checked_rows = 0

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("| Capability Set |"):
            in_table = True
            continue
        if not in_table:
            continue
        if line.startswith("| :---"):
            continue
        if not line.startswith("|"):
            break
        match = ROW_RE.match(line)
        if not match:
            continue
        capability, _, refs_col = match.groups()
        refs = [_normalize_ref(r) for r in REF_RE.findall(refs_col)]
        checked_rows += 1
        if not refs:
            errors.append(f"[{capability.strip()}] has no backtick-wrapped references")
            continue
        for ref in refs:
            if not _verify_ref_exists(ref):
                errors.append(f"[{capability.strip()}] reference does not exist: {ref}")

    if checked_rows == 0:
        errors.append("no capability rows were parsed from matrix")

    if errors:
        print("Capability matrix verification FAILED:")
        for err in errors:
            print(f"- {err}")
        return 2

    print(f"Capability matrix verification OK ({checked_rows} rows).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
