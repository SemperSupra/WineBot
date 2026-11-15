"""Source-contract tests for opt-in disposable runtime/app/state layout.

These tests use only stdlib and deliberately do not provision real users.
An independent public Actions job performs disposable Docker replay.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DisposableAppBundleSourceTests(unittest.TestCase):
    def test_builder_requires_offline_manifest_and_rejects_symlinks(self):
        src = (ROOT / "docker/app-bundle.Dockerfile").read_text(encoding="utf-8")
        self.assertIn("FROM ${APP_PACK_BUILDER_IMAGE}", src)
        self.assertIn("debian@sha256:", src)
        self.assertIn("find /opt/winebot/app-payload -type l", src)
        self.assertIn("app-manifest.sha256", src)
        self.assertIn("COPY apps/", src)
        for forbidden in ("apt-get", "curl ", "wget ", "ADD https://", "docker push"):
            self.assertNotIn(forbidden, src)

    def test_seed_is_idempotent_and_never_replaces_existing_apps(self):
        src = (ROOT / "scripts/layers/seed-apps.sh").read_text(encoding="utf-8")
        for marker in ("stage=existing_verified", "stage=created_verified",
                       "version_mismatch", "integrity_mismatch",
                       "incomplete_volume", "sha256sum -c", "set -eu"):
            self.assertIn(marker, src)
        self.assertLess(src.index('if [ -f "$stamp" ]; then'),
                        src.index('cp -a "$source_dir"/.'))
        for forbidden in ("rm -rf", "curl ", "wget ", "docker push"):
            self.assertNotIn(forbidden, src)


if __name__ == "__main__":
    unittest.main()
