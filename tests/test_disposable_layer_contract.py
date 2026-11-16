"""Source-contract tests for opt-in disposable runtime/app/state layout.

These tests use only stdlib and deliberately do not provision real users.
An independent public Actions job performs disposable Docker replay.
"""
import unittest
from pathlib import Path

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
        self.assertIn("fail unexpected_files", src)
        self.assertIn("fail unexpected_symlink", src)
        self.assertIn('mkdir "$lock"', src)
        self.assertIn('fail concurrent_init', src)
        self.assertIn('fail permissions_failed', src)
        self.assertIn('[ -e "$lock" ] && fail concurrent_init', src)
        self.assertLess(src.index('verify_inventory() {'),
                        src.index('if [ -f "$stamp" ]; then'))
        for forbidden in ("rm -rf", "curl ", "wget ", "docker push"):
            self.assertNotIn(forbidden, src)


    def test_external_volumes_and_disposable_runtime_are_enforced(self):
        source = (ROOT / "compose/layered.yml").read_text(encoding="utf-8")
        self.assertEqual(source.count("external: true"), 7)
        self.assertIn("condition: service_completed_successfully", source)
        self.assertIn("read_only: true", source)
        self.assertIn("user: \"1000:1000\"", source)
        self.assertIn("source: app-store", source)
        self.assertIn("target: /apps", source)
        self.assertIn("read_only: true", source)
        # Every runtime state/app volume refuses Docker image copy-up, or
        # Compose may initialize/chown it before one-shot seed/state services.
        self.assertEqual(source.count("nocopy: true"), 7)
        self.assertIn("WINEBOT_STATE_MODEL: layered", source)
        self.assertIn("WINEBOT_INPUT_TRACE_WINDOWS: \"1\"", source)
        self.assertIn("127.0.0.1:8000:8000", source)
        self.assertNotIn("    build:", source)
        self.assertNotIn("actions/upload-artifact@", source)

    def test_layered_api_is_enabled_without_unauthenticated_fallback(self):
        compose = (ROOT / "compose/layered.yml").read_text(encoding="utf-8")
        start = (ROOT / "scripts/init/30-start-services.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('if [ "${ENABLE_API:-0}" = "1" ]; then', start)
        self.assertIn('      ENABLE_API: "1"', compose)
        self.assertIn("API_TOKEN: ${WINEBOT_API_TOKEN:", compose)
        self.assertIn('TOKENS="$$(cat /tmp/winebot_api_token', compose)
        self.assertIn('X-API-Key: $$TOKEN', compose)
        self.assertIn(
            'curl -fsS -H "X-API-Key: $$TOKEN" http://127.0.0.1:8000/health',
            compose,
        )
        self.assertNotIn('curl -fsS http://127.0.0.1:8000/health', compose)
        self.assertNotIn('curl -fsS http://localhost:8000/health', compose)

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
        self.assertLess(source.index('chmod u+rwx "$dir"'),
                        source.index('chown 1000:1000 "$dir"'))

    def test_deployment_preflight_never_prunes_external_volumes(self):
        src = (ROOT / "scripts/layers/preflight.sh").read_text(encoding="utf-8")
        self.assertIn("docker volume inspect", src)
        self.assertIn("docker volume create", src)
        self.assertIn("stage=unpinned_image", src)
        self.assertNotIn("docker volume rm", src)
        self.assertNotIn("docker system prune", src)

    def test_tool_builder_uses_immutable_image_digest(self):
        src = (ROOT / "docker/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("TOOL_BUILDER_BASE_IMAGE=debian@sha256:", src)
        self.assertIn("FROM ${TOOL_BUILDER_BASE_IMAGE} AS tool-base", src)
        self.assertNotIn("FROM debian:trixie-slim AS tool-base", src)

    def test_actual_unit_manifest_includes_layer_contract(self):
        src = (ROOT / "scripts/ci/test.sh").read_text(encoding="utf-8")
        self.assertIn("tests/test_disposable_layer_contract.py", src)


    def test_wine11_hil_is_public_disposable_and_provenance_bound(self):
        wf = (ROOT / ".github/workflows/wine11-disposable-layer-hil.yml").read_text(
            encoding="utf-8"
        )
        script = (ROOT / "scripts/ci/qualify-wine11-layered.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("runs-on: ubuntu-24.04", wf)
        self.assertIn("d2304d2b2e096a097ffa76b79aeaeef85b72d702", wf)
        self.assertIn("persist-credentials: false", wf)
        self.assertIn("DOCKER_BUILD_RECORD_UPLOAD: 'false'", wf)
        self.assertNotIn("actions/upload-artifact@", wf)
        self.assertNotIn("push: true", wf)
        self.assertIn("fail health_recreate", script)
        self.assertIn("fail state_replay", script)
        self.assertIn("kill -s SIGKILL winebot-interactive", script)
        self.assertIn("fault_exit_not_sigkill", script)
        self.assertIn("fail fault_health", script)
        self.assertIn("fail fault_state_replay", script)
        self.assertIn("DURATION_SECONDS=90", script)
        self.assertIn("--read-only", (ROOT / "compose/layered.yml").read_text(
            encoding="utf-8"
        ).replace("read_only: true", "--read-only"))
        self.assertNotIn("docker volume prune", script)

if __name__ == "__main__":
    unittest.main()
