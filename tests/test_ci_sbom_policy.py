import json
import subprocess
import os
from pathlib import Path


def test_generate_validate_and_license_policy_scripts(tmp_path: Path):
    sbom_path = tmp_path / "python-sbom.cdx.json"

    subprocess.run(
        [
            "python3",
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
        ["python3", "scripts/ci/validate-sbom.py", "--input", str(sbom_path)],
        check=True,
    )
    subprocess.run(
        [
            "python3",
            "scripts/ci/check-license-policy.py",
            "--input",
            str(sbom_path),
        ],
        env={**os.environ, "WINEBOT_LICENSE_DENY": "__NO_MATCH__", "WINEBOT_LICENSE_ALLOW_UNKNOWN": "1"},
        check=True,
    )
