#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List


DEFAULT_DENY = "GPL-2.0,GPL-3.0,AGPL,SSPL,COMMONS-CLAUSE"


def _deny_tokens() -> List[str]:
    raw = os.getenv("WINEBOT_LICENSE_DENY", DEFAULT_DENY)
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


def _allow_unknown() -> bool:
    raw = (os.getenv("WINEBOT_LICENSE_ALLOW_UNKNOWN", "1") or "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _license_names(component: Dict[str, Any]) -> Iterable[str]:
    licenses = component.get("licenses")
    if not isinstance(licenses, list):
        return []
    values: List[str] = []
    for item in licenses:
        if not isinstance(item, dict):
            continue
        license_obj = item.get("license")
        if not isinstance(license_obj, dict):
            continue
        name = license_obj.get("id") or license_obj.get("name")
        if name:
            values.append(str(name))
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce license deny policy against CycloneDX SBOM")
    parser.add_argument("--input", required=True, help="SBOM JSON file path")
    args = parser.parse_args()

    path = Path(args.input)
    if not path.exists():
        raise SystemExit(f"license policy failed: file not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    components = payload.get("components")
    if not isinstance(components, list):
        raise SystemExit("license policy failed: components list missing")

    deny = _deny_tokens()
    allow_unknown = _allow_unknown()
    violations: List[str] = []
    unknown: List[str] = []
    for component in components:
        if not isinstance(component, dict):
            continue
        name = str(component.get("name") or "unknown")
        version = str(component.get("version") or "")
        licenses = [lic.strip() for lic in _license_names(component) if lic.strip()]
        if not licenses:
            unknown.append(f"{name}@{version}")
            continue
        for license_name in licenses:
            upper = license_name.upper()
            if any(token in upper for token in deny):
                violations.append(f"{name}@{version}: {license_name}")

    if violations:
        joined = "\n".join(sorted(violations))
        raise SystemExit(f"license policy failed (deny list match):\n{joined}")

    if unknown and not allow_unknown:
        joined = "\n".join(sorted(unknown))
        raise SystemExit(f"license policy failed (unknown licenses):\n{joined}")

    print(
        f"license policy: OK ({path}) deny_tokens={','.join(deny)} unknown={len(unknown)} allow_unknown={int(allow_unknown)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
