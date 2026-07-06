#!/usr/bin/env python3
import argparse
import datetime
import importlib.metadata
import json
import os
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

try:
    from packaging.requirements import Requirement
except Exception:  # pragma: no cover - fallback keeps the script dependency-light
    Requirement = None  # type: ignore[assignment]

DEFAULT_REQUIREMENT_FILES = [
    Path("requirements/requirements-rel.txt"),
    Path("requirements/requirements-devtest.txt"),
]


def _canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_name(requirement: str) -> str | None:
    if Requirement is not None:
        try:
            parsed = Requirement(requirement)
            if parsed.marker is not None and not parsed.marker.evaluate({"extra": ""}):
                return None
            return _canonical_name(parsed.name)
        except Exception:
            pass

    match = re.match(r"\s*([A-Za-z0-9_.-]+)", requirement)
    if not match:
        return None
    return _canonical_name(match.group(1))


def _roots_from_requirements(paths: Iterable[Path]) -> set[str]:
    roots: set[str] = set()
    for path in paths:
        if not path.exists():
            print(f"sbom: warning: requirements file not found: {path}", file=sys.stderr)
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or line.startswith(("-", "git+", "http://", "https://")):
                continue
            name = _requirement_name(line)
            if name:
                roots.add(name)
    return roots


def _component_for_distribution(dist: importlib.metadata.Distribution) -> dict[str, Any]:
    metadata = dist.metadata
    name = metadata.get("Name") or dist.name or "unknown"
    version = dist.version or "0"
    license_name = (metadata.get("License") or "").strip() or "NOASSERTION"
    component: dict[str, Any] = {
        "type": "library",
        "name": str(name),
        "version": str(version),
        "licenses": [{"license": {"name": license_name}}],
        "purl": f"pkg:pypi/{str(name).lower()}@{str(version)}",
    }
    return component


def _all_distributions_by_name() -> dict[str, importlib.metadata.Distribution]:
    distributions: dict[str, importlib.metadata.Distribution] = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get("Name") or dist.name
        if name:
            distributions[_canonical_name(str(name))] = dist
    return distributions


def _selected_distributions(
    distributions: dict[str, importlib.metadata.Distribution],
    roots: set[str],
) -> list[importlib.metadata.Distribution]:
    selected: dict[str, importlib.metadata.Distribution] = {}
    queue = list(sorted(roots))
    visited: set[str] = set()

    while queue:
        name = queue.pop(0)
        if name in visited:
            continue
        visited.add(name)
        dist = distributions.get(name)
        if dist is None:
            print(f"sbom: warning: installed distribution not found for requirement: {name}", file=sys.stderr)
            continue

        selected[name] = dist
        for requirement in dist.requires or []:
            dependency = _requirement_name(requirement)
            if dependency and dependency not in visited:
                queue.append(dependency)

    return sorted(selected.values(), key=lambda d: (d.metadata.get("Name") or d.name or "").lower())


def build_sbom(requirement_files: Iterable[Path] | None = None, *, all_installed: bool = False) -> dict[str, Any]:
    distributions = _all_distributions_by_name()
    if all_installed:
        selected = sorted(distributions.values(), key=lambda d: (d.metadata.get("Name") or d.name or "").lower())
    else:
        roots = _roots_from_requirements(requirement_files or DEFAULT_REQUIREMENT_FILES)
        selected = _selected_distributions(distributions, roots)

    components: list[dict[str, Any]] = []
    for dist in selected:
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
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
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
    parser.add_argument(
        "--requirements",
        action="append",
        type=Path,
        help="Requirement file to use as a dependency root. Defaults to runtime plus dev/test pins.",
    )
    parser.add_argument(
        "--all-installed",
        action="store_true",
        help="Include every installed Python distribution in the executing interpreter.",
    )
    args = parser.parse_args()

    payload = build_sbom(args.requirements, all_installed=args.all_installed)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"sbom: wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
