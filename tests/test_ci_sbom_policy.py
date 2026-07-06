import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType


def _load_sbom_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "generate_python_sbom",
        Path("scripts/ci/generate-python-sbom.py"),
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeDistribution:
    def __init__(
        self,
        name: str,
        version: str,
        license_name: str,
        requires: list[str] | None = None,
    ):
        self.metadata = {"Name": name, "License": license_name}
        self.name = name
        self.version = version
        self.requires = requires or []


def test_generate_validate_and_license_policy_scripts(tmp_path: Path):
    sbom_path = tmp_path / "python-sbom.cdx.json"

    subprocess.run(
        [
            sys.executable,
            "scripts/ci/generate-python-sbom.py",
            "--output",
            str(sbom_path),
        ],
        check=True,
    )
    assert sbom_path.exists()

    payload = json.loads(sbom_path.read_text(encoding="utf-8"))
    assert payload["bomFormat"] == "CycloneDX"
    assert payload["specVersion"] == "1.5"

    subprocess.run(
        [sys.executable, "scripts/ci/validate-sbom.py", "--input", str(sbom_path)],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            "scripts/ci/check-license-policy.py",
            "--input",
            str(sbom_path),
        ],
        env={**os.environ, "WINEBOT_LICENSE_DENY": "__NO_MATCH__", "WINEBOT_LICENSE_ALLOW_UNKNOWN": "1"},
        check=True,
    )


def test_generate_sbom_scopes_to_requirement_closure(tmp_path: Path, monkeypatch):
    sbom = _load_sbom_module()
    req = tmp_path / "requirements.txt"
    req.write_text("rootpkg==1.0\n", encoding="utf-8")

    fake_distributions = [
        FakeDistribution("rootpkg", "1.0", "MIT", ["dep_pkg>=2"]),
        FakeDistribution("dep-pkg", "2.0", "Apache-2.0"),
        FakeDistribution("unrelated-gpl-tool", "9.9", "GPL-3.0"),
    ]
    monkeypatch.setattr(sbom.importlib.metadata, "distributions", lambda: fake_distributions)

    payload = sbom.build_sbom([req])
    names = {component["name"] for component in payload["components"]}

    assert names == {"rootpkg", "dep-pkg"}


def test_generate_sbom_skips_inactive_optional_requirements(tmp_path: Path, monkeypatch):
    sbom = _load_sbom_module()
    req = tmp_path / "requirements.txt"
    req.write_text("rootpkg==1.0\n", encoding="utf-8")

    fake_distributions = [
        FakeDistribution("rootpkg", "1.0", "MIT", ['optional-gpl; extra == "dev"']),
        FakeDistribution("optional-gpl", "9.9", "GPL-3.0"),
    ]
    monkeypatch.setattr(sbom.importlib.metadata, "distributions", lambda: fake_distributions)

    payload = sbom.build_sbom([req])
    names = {component["name"] for component in payload["components"]}

    assert names == {"rootpkg"}
