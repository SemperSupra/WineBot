#!/usr/bin/env python3
"""Project exactly five provisional vNext slices to public numeric counts only."""
from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path

LABELS = ("portable_core_candidate", "capability_extension_candidate",
          "implementation_specific", "obsolete_contract", "unresolved")
SAN = runpy.run_path(str(Path(__file__).with_name("sanitize-conformance-results.py")))
PROJECT = SAN["project_public_result"]
MAX_BYTES = SAN["MAX_RAW_BYTES"]


def project_slices(raw_dir: Path) -> dict:
    slices = []
    for label in LABELS:
        path = raw_dir / f"vnext-internal-{label}.json"
        entry = {"slice": label, "status": "missing"}
        try:
            if path.is_symlink():
                raise ValueError("symlink")
            if path.is_file():
                if path.stat().st_size > MAX_BYTES:
                    raise ValueError("oversize")
                projected = PROJECT(json.loads(path.read_text(encoding="utf-8")))
                entry = {"slice": label, "status": "validated",
                         "summary": projected["summary"]}
        except (ValueError, UnicodeError, OSError):
            entry = {"slice": label, "status": "invalid"}
        slices.append(entry)
    return {"schema": "winebot.public-vnext-slices.v1",
            "provisional": True, "native_acceptance": False, "slices": slices}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    public = project_slices(args.raw_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(public, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print("Safe provisional vNext numerical counts projected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
