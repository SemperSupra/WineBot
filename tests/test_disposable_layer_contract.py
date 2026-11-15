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


    def test_external_volumes_and_disposable_runtime_are_enforced(self):
        source = (ROOT / "compose/layered.yml").read_text(encoding="utf-8")
        self.assertEqual(source.count("external: true"), 7)
        self.assertIn("condition: service_completed_successfully", source)
        self.assertIn("read_only: true", source)
        self.assertIn("user: \"1000:1000\"", source)
        self.assertIn("app-store:/apps:ro", source)
        self.assertIn("WINEBOT_STATE_MODEL: layered", source)
        self.assertIn("WINEBOT_INPUT_TRACE_WINDOWS: \"1\"", source)
        self.assertIn("127.0.0.1:8000:8000", source)
        self.assertNotIn("    build:", source)
        self.assertNotIn("actions/upload-artifact@", source)

    def test_layered_entrypoint_fail_closed_without_legacy_impact(self):
        source = (ROOT / "docker/entrypoint.sh").read_text(encoding="utf-8")
        self.assertIn('WINEBOT_STATE_MODEL:-legacy', source)
        self.assertIn("stage=runtime_install_forbidden", source)
        self.assertIn("stage=persistent_mount_unavailable", source)
        self.assertIn("stage=app_mount_invalid", source)
        self.assertIn('WINEBOT_CONFIG_FILE="/config/winebot.env"', source)
        self.assertIn('WINEBOT_CONFIG_FILE="/wineprefix/winebot.env"', source)

    def test_state_preparer_does_not_recurse_or_remove_user_data(self):
        source = (ROOT / "scripts/layers/prepare-state.sh").read_text(encoding="utf-8")
        self.assertIn("chown 1000:1000", source)
        self.assertNotIn("chown -R", source)
        self.assertNotIn("rm -rf", source)

    def test_deployment_preflight_never_prunes_external_volumes(self):
        src = (ROOT / "scripts/layers/preflight.sh").read_text(encoding="utf-8")
        self.assertIn("docker volume inspect", src)
        self.assertIn("docker volume create", src)
        self.assertIn("stage=unpinned_image", src)
        self.assertNotIn("docker volume rm", src)
        self.assertNotIn("docker system prune", src)

if __name__ == "__main__":
    unittest.main()
