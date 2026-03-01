#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Any, Dict


class ValidationError(Exception):
    pass


def _require(value: Any, message: str) -> None:
    if not value:
        raise ValidationError(message)


def validate_cyclonedx_15(payload: Dict[str, Any]) -> None:
    _require(payload.get("bomFormat") == "CycloneDX", "bomFormat must be CycloneDX")
    _require(str(payload.get("specVersion", "")) == "1.5", "specVersion must be 1.5")
    _require(isinstance(payload.get("version"), int), "version must be an integer")

    metadata = payload.get("metadata")
    _require(isinstance(metadata, dict), "metadata must be an object")
    component = metadata.get("component") if isinstance(metadata, dict) else None
    _require(isinstance(component, dict), "metadata.component must be an object")
    _require(component.get("name"), "metadata.component.name is required")
    _require(component.get("version"), "metadata.component.version is required")

    components = payload.get("components")
    _require(isinstance(components, list), "components must be a list")
    for idx, item in enumerate(components):
        if not isinstance(item, dict):
            raise ValidationError(f"components[{idx}] must be an object")
        _require(item.get("name"), f"components[{idx}].name is required")
        _require(item.get("version"), f"components[{idx}].version is required")
        _require(item.get("type"), f"components[{idx}].type is required")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate CycloneDX SBOM schema essentials")
    parser.add_argument("--input", required=True, help="SBOM JSON file path")
    args = parser.parse_args()

    path = Path(args.input)
    if not path.exists():
        raise SystemExit(f"sbom validation failed: file not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        validate_cyclonedx_15(payload)
    except ValidationError as exc:
        raise SystemExit(f"sbom validation failed: {exc}") from exc

    print(f"sbom validation: OK ({path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
