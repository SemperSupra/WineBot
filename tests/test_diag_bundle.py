import json
import os
import subprocess
import tarfile
from pathlib import Path


def _extract_bundle(bundle_path: Path, out_dir: Path) -> Path:
    with tarfile.open(bundle_path, "r:gz") as tf:
        tf.extractall(out_dir)
    return out_dir / "support-bundle"


def test_diag_bundle_redacts_and_writes_manifest(tmp_path: Path):
    session = tmp_path / "sessions" / "session-1"
    logs = session / "logs"
    logs.mkdir(parents=True)
    (session / "session.json").write_text(json.dumps({"session_id": "abc-123"}))
    (logs / "api.log").write_text("Authorization: Bearer SECRET123\nX-API-Key: SECRET123\n")

    out = tmp_path / "bundle.tar.gz"
    env = os.environ.copy()
    env["API_TOKEN"] = "SECRET123"
    env["BUILD_INTENT"] = "rel"

    subprocess.run(
        [
            "python3",
            "scripts/diag_bundle.py",
            "--session-dir",
            str(session),
            "--out",
            str(out),
            "--max-mb",
            "50",
        ],
        check=True,
        env=env,
    )

    bundle_root = _extract_bundle(out, tmp_path / "extract")
    manifest = json.loads((bundle_root / "manifest.json").read_text())
    assert manifest["schema_version"] == "1.0"
    assert manifest["build_intent"] == "rel"
    assert manifest["redaction_version"] == "1"
    assert any(item["path"] == "system/env.redacted.json" for item in manifest["files"])

    api_log = (bundle_root / "app" / "logs" / "api.log").read_text()
    assert "SECRET123" not in api_log
    assert "***REDACTED***" in api_log


def test_diag_bundle_size_cap_enforced(tmp_path: Path):
    session = tmp_path / "sessions" / "session-2"
    logs = session / "logs"
    logs.mkdir(parents=True)
    (session / "session.json").write_text(json.dumps({"session_id": "abc-999"}))
    (logs / "huge.log").write_text("A" * (2 * 1024 * 1024))

    out = tmp_path / "bundle-too-small.tar.gz"
    proc = subprocess.run(
        [
            "python3",
            "scripts/diag_bundle.py",
            "--session-dir",
            str(session),
            "--out",
            str(out),
            "--max-mb",
            "1",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "size cap exceeded" in (proc.stderr + proc.stdout)
