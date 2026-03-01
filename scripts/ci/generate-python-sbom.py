#!/usr/bin/env python3
import argparse
import datetime
import importlib.metadata
import json
import os
from pathlib import Path
from typing import Any, Dict, List


def _component_for_distribution(dist: importlib.metadata.Distribution) -> Dict[str, Any]:
    metadata = dist.metadata
    name = metadata.get("Name") or dist.name or "unknown"
    version = dist.version or "0"
    license_name = (metadata.get("License") or "").strip() or "NOASSERTION"
    component: Dict[str, Any] = {
        "type": "library",
        "name": str(name),
        "version": str(version),
        "licenses": [{"license": {"name": license_name}}],
        "purl": f"pkg:pypi/{str(name).lower()}@{str(version)}",
    }
    return component


def build_sbom() -> Dict[str, Any]:
    components: List[Dict[str, Any]] = []
    for dist in sorted(importlib.metadata.distributions(), key=lambda d: (d.metadata.get("Name") or d.name or "").lower()):
        try:
            components.append(_component_for_distribution(dist))
        except Exception:
            continue

    version = "0.0.0"
    version_file = Path("VERSION")
    if version_file.exists():
        version = version_file.read_text(encoding="utf-8").strip() or version

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{os.urandom(16).hex()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "component": {
                "type": "application",
                "name": "winebot",
                "version": version,
            },
            "tools": [
                {
                    "vendor": "WineBot",
                    "name": "generate-python-sbom",
                    "version": "1",
                }
            ],
        },
        "components": components,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Python dependency CycloneDX SBOM")
    parser.add_argument(
        "--output",
        default="artifacts/ci/python-sbom.cdx.json",
        help="Output JSON path",
    )
    args = parser.parse_args()

    payload = build_sbom()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"sbom: wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
