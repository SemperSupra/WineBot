"""Source-level regression for isolated unit CI and safe startup diagnostics."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class CIUnitIsolationTests(unittest.TestCase):
    def test_units_do_not_start_interactive_runtime(self):
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        unit = "--profile test --profile interactive run --rm --no-deps test-runner scripts/ci/test.sh"
        startup = "up --detach --wait --wait-timeout 150 winebot-interactive"
        e2e = "pytest -q /work/tests/e2e/test_dashboard_e2e.py"
        self.assertEqual(source.count(unit), 1)
        self.assertEqual(source.count(startup), 1)
        self.assertLess(source.index(unit), source.index(startup))
        self.assertLess(source.index(startup), source.index(e2e))
        self.assertIn("Stop E2E runtime", source)
        self.assertIn("if: always()", source)

    def test_failed_startup_emits_only_bounded_markers(self):
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("Classify failed interactive startup without printing service logs", source)
        self.assertIn("python3 scripts/ci/classify-startup-logs.py", source)
        self.assertIn('STARTUP_DIAGNOSTIC stage=', (ROOT / "scripts/ci/classify-startup-logs.py").read_text(encoding="utf-8"))
        self.assertIn("State.OOMKilled", source)
        self.assertNotIn("docker compose -f compose/docker-compose.yml logs --tail", source)

    def test_entrypoint_stage_is_fixed_and_cleared_at_ready(self):
        source = (ROOT / "docker/entrypoint.sh").read_text(encoding="utf-8")
        for marker in ('WINEBOT_STARTUP_STAGE="configuration"',
                       'WINEBOT_STARTUP_STAGE="infrastructure"',
                       'WINEBOT_STARTUP_STAGE="wine"',
                       'WINEBOT_STARTUP_STAGE="services"',
                       "WINEBOT_STARTUP_ERROR stage=%s",
                       "trap - EXIT"):
            self.assertIn(marker, source)
        self.assertLess(source.index('WINEBOT_STARTUP_STAGE="services"'),
                        source.index("trap - EXIT"))

    def test_classifier_redacts_untrusted_log_contents(self):
        import subprocess
        import sys

        marker = "SYNTHETIC-CREDENTIAL-NOT-FOR-RELEASE"
        output = subprocess.run(
            [sys.executable, str(ROOT / "scripts/ci/classify-startup-logs.py")],
            input=marker + "\\nWINEBOT_STARTUP_ERROR stage=services/trace-log-path rc=1\\n",
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        self.assertEqual(output.strip(), "STARTUP_DIAGNOSTIC stage=failed_trace_log_path")
        self.assertNotIn(marker, output)

    def test_wine_ci_runner_image_pinned_to_qualified_public_venue(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        reusable = (ROOT / ".github/workflows/reusable-build-smoke-gate.yml").read_text(
            encoding="utf-8"
        )
        self.assertEqual(ci.count("runs-on: ubuntu-24.04"), 2)
        self.assertEqual(reusable.count("runs-on: ubuntu-24.04"), 1)
        self.assertNotIn("runs-on: ubuntu-latest", ci)
        self.assertNotIn("runs-on: ubuntu-latest", reusable)

    def test_top_level_cli_resolves_shared_profile_catalog(self):
        import os
        import subprocess

        env = os.environ.copy()
        env["WINEBOT_API_TOKEN"] = "SYNTHETIC_TEST_TOKEN_123456"
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/winebotctl"), "--help"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr[:200])
        self.assertIn("WineBot unified CLI", result.stdout)

    def test_nightly_soak_is_pinned_to_public_qualified_venue(self):
        nightly = (ROOT / ".github/workflows/nightly-soak.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("runs-on: ubuntu-24.04", nightly)
        self.assertNotIn("runs-on: ubuntu-latest", nightly)

    def test_health_wait_failure_output_is_allowlisted(self):
        source = (ROOT / "scripts/ci/wait-for-container-health.sh").read_text(
            encoding="utf-8"
        )
        self.assertEqual(source.count("diagnose_health_failure"), 3)
        self.assertIn('python3 "$classifier"', source)
        self.assertIn('logs --no-color --tail 200 "$service" 2>/dev/null', source)
        self.assertNotIn('logs --tail 200 "$service" || true', source)


    def test_nightly_uses_exact_prebuilt_rel_image(self):
        nightly = (ROOT / ".github/workflows/nightly-soak.yml").read_text(encoding="utf-8")
        compose = (ROOT / "compose/docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("tags: winebot:local-rel", nightly)
        self.assertIn("WINEBOT_IMAGE_VERSION: 'local'", nightly)
        self.assertIn("BUILD_INTENT: 'rel'", nightly)
        self.assertIn(
            "image: winebot:$" + "{WINEBOT_IMAGE_VERSION:-local}-$" + "{BUILD_INTENT:-rel}",
            compose,
        )
        self.assertIn(
            "--profile interactive up --no-build -d winebot-interactive", nightly
        )

    def test_nightly_resource_budget_is_passed_to_soak_container(self):
        nightly = (ROOT / ".github/workflows/nightly-soak.yml").read_text(encoding="utf-8")
        for key in ("DURATION_SECONDS", "INTERVAL_SECONDS", "MAX_LOG_MB", "MAX_SESSION_MB"):
            self.assertIn('-e ' + key + '="$' + key + '"', nightly)

    def test_nightly_trust_pack_remains_job_local(self):
        nightly = (ROOT / ".github/workflows/nightly-soak.yml").read_text(encoding="utf-8")
        self.assertIn("Security hold: trust-pack evidence stays job-local", nightly)
        self.assertNotIn("actions/upload-artifact@", nightly)

    def test_focused_workflow_covers_runtime_safety_changes(self):
        workflow = (ROOT / ".github/workflows/ci-unit-isolation.yml").read_text(encoding="utf-8")
        for path in (".github/workflows/nightly-soak.yml",
                     "scripts/ci/wait-for-container-health.sh",
                     "scripts/bin/winebotctl", "scripts/winebotctl"):
            self.assertIn(f"      - '{path}'", workflow)

    def test_health_waiter_never_echoes_sensitive_service_log_content(self):
        import os
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            mock_docker = Path(directory) / "docker"
            mock_docker.write_text(
                """#!/bin/sh
case "$1" in
  inspect) printf '%s\\n' unhealthy;;
  compose)
    case " $* " in
      *" ps -q "*) printf '%s\\n' mock123;;
      *" logs "*) printf '%s\\n' SYNTHETIC_SECRET 'WINEBOT_STARTUP_ERROR stage=services/trace-log-path rc=1';;
      *) exit 4;;
    esac;;
  *) exit 4;;
esac
""",
                encoding="utf-8",
            )
            mock_docker.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = directory + os.pathsep + env["PATH"]
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/ci/wait-for-container-health.sh"),
                 "compose/docker-compose.yml", "interactive",
                 "winebot-interactive", "1", "1"],
                env=env, capture_output=True, text=True, timeout=10, check=False
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("STARTUP_DIAGNOSTIC stage=failed_trace_log_path",
                          result.stdout + result.stderr)
            self.assertNotIn("SYNTHETIC_SECRET", result.stdout + result.stderr)
            self.assertNotIn("mock123", result.stdout + result.stderr)


    def test_exact_nightly_rel_startup_public_qualifier(self):
        source = (ROOT / ".github/workflows/nightly-rel-startup-qualification.yml").read_text(
            encoding="utf-8"
        )
        nightly = (ROOT / ".github/workflows/nightly-soak.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("runs-on: ubuntu-24.04", source)
        self.assertIn("DOCKER_BUILD_RECORD_UPLOAD: 'false'", source)
        for marker in ("--target intent-rel", "--build-arg BUILD_INTENT=rel",
                       "--tag winebot:local-rel",
                       "--profile interactive up --no-build -d winebot-interactive",
                       "wait-for-container-health.sh compose/docker-compose.yml interactive winebot-interactive 120 2"):
            self.assertIn(marker, source)
        for marker in ("target: intent-rel", "BUILD_INTENT=rel",
                       "tags: winebot:local-rel",
                       "--profile interactive up --no-build -d winebot-interactive",
                       "wait-for-container-health.sh compose/docker-compose.yml interactive winebot-interactive 120 2"):
            self.assertIn(marker, nightly)
        self.assertIn("WINEBOT_INPUT_TRACE_WINDOWS: '1'", source)
        self.assertIn("Classify failure without printing raw service logs", source)
        self.assertIn("python3 scripts/ci/classify-startup-logs.py", source)
        self.assertNotIn("actions/upload-artifact@", source)
        self.assertNotIn("push: true", source)


    def test_exact_rel_image_is_major_version_11_in_both_venues(self):
        qualifier = (
            ROOT / ".github/workflows/nightly-rel-startup-qualification.yml"
        ).read_text(encoding="utf-8")
        nightly = (ROOT / ".github/workflows/nightly-soak.yml").read_text(
            encoding="utf-8"
        )
        for source in (qualifier, nightly):
            self.assertIn("Require verified Wine 11 runtime from exact REL image", source)
            self.assertIn(
                "docker run --rm --entrypoint wine winebot:local-rel --version",
                source,
            )
            self.assertIn("wine-11|wine-11.*)", source)
            self.assertIn("WINE_RUNTIME_DIAGNOSTIC stage=major_mismatch", source)
            self.assertNotIn('echo "$version"', source)


    def test_wine11_candidate_has_scoped_signed_repo_and_pinned_stable_package(self):
        base = (ROOT / "docker/base.Dockerfile").read_text(encoding="utf-8")
        self.assertIn(
            "D43F640145369C51D786DDEA76F1A20FF987672F", base
        )
        self.assertIn("winehq-stable=11.0.0.0~trixie-1", base)
        self.assertIn("Signed-By: /etc/apt/keyrings/winehq-archive.gpg", base)
        self.assertIn("Suites: trixie", base)
        self.assertNotIn("wine wine64 wine32 cabextract", base)
        self.assertIn("wine --version | grep -Eq '^wine-11([.]|$)'", base)

    def test_wine11_candidate_uses_local_public_runner_with_no_image_publishing(self):
        candidate = (
            ROOT / ".github/workflows/nightly-rel-startup-qualification.yml"
        ).read_text(encoding="utf-8")
        manual = (ROOT / ".github/workflows/base-image.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("winebot-base:wine11-candidate", candidate)
        self.assertIn("file: docker/base.Dockerfile", candidate)
        self.assertIn("--build-arg BASE_IMAGE=winebot-base:wine11-candidate", candidate)
        self.assertIn("ref: " + "$" + "{{ github.event.pull_request.head.sha }}", candidate)
        self.assertIn("push: false", candidate)
        self.assertNotIn("push: true", candidate)
        self.assertNotIn("actions/upload-artifact@", candidate)
        self.assertIn("Require Wine 11 base identity before image publication", manual)
        self.assertIn("runs-on: ubuntu-24.04", manual)

    def test_generated_api_token_is_not_ever_echoed(self):
        source = (ROOT / "scripts/init/30-start-services.sh").read_text(encoding="utf-8")
        self.assertNotIn("Generated random token: ${API_TOKEN}", source)
        self.assertIn("value not logged", source)
        self.assertIn('echo -n "$API_TOKEN" > /tmp/winebot_api_token', source)


    def test_wine11_new_prefix_is_initialized_without_template_clone(self):
        source = (ROOT / "scripts/init/20-setup-wine.sh").read_text(encoding="utf-8")
        self.assertIn('if [ "${INIT_PREFIX:-1}" = "1" ] && [ ! -f "$WINEPREFIX/system.reg" ]; then', source)
        self.assertIn("if wine --version 2>/dev/null | grep -Eq '^wine-11([.]|$)'; then", source)
        self.assertIn("WINEBOT_STARTUP_STAGE=\"wine/prefix-init\"", source)
        self.assertIn("WINE_PREFIX_DIAGNOSTIC stage=init_failed", source)
        self.assertIn("WINE_PREFIX_DIAGNOSTIC stage=clone_failed", source)
        self.assertEqual(source.count("timeout -k 5s 90s env WINEDLLOVERRIDES=mscoree,mshtml= wineboot -i >/dev/null 2>&1"), 1)
        self.assertEqual(source.count("timeout -k 5s 90s wineboot -u >/dev/null 2>&1"), 1)
        base = (ROOT / "docker/base.Dockerfile").read_text(encoding="utf-8")
        self.assertIn("if ! timeout -k 5s 120s env WINEDLLOVERRIDES=mscoree,mshtml= wineboot -i >/dev/null 2>&1; then", base)
        self.assertIn("WINE_BASE_PREFIX_DIAGNOSTIC stage=wineboot_failed", base)
        self.assertIn("WINE_BASE_PREFIX_DIAGNOSTIC stage=registry_missing", base)
        self.assertNotIn("&& wineboot -u " + "\\", base)
        self.assertLess(source.index("if wine --version"), source.index('elif [ -d "/opt/winebot/prefix-template" ]'))
        self.assertLess(source.index("WINEBOT_STARTUP_STAGE=\"wine/prefix-init\""), source.index("WINEBOT_STARTUP_STAGE=\"wine/prefix-clone\""))
        for workflow in ("ci-unit-isolation.yml", "nightly-rel-startup-qualification.yml"):
            text = (ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8")
            self.assertIn("      - 'scripts/init/20-setup-wine.sh'", text)

    def test_wine11_preflight_is_disposable_redacted_and_before_compose(self):
        workflow = (ROOT / ".github/workflows/nightly-rel-startup-qualification.yml").read_text(
            encoding="utf-8"
        )
        probe = (ROOT / "scripts/ci/probe-wine11-prefix.sh").read_text(encoding="utf-8")
        self.assertIn("      - 'scripts/ci/probe-wine11-prefix.sh'", workflow)
        self.assertIn("bash scripts/ci/probe-wine11-prefix.sh", workflow)
        self.assertLess(
            workflow.index("bash scripts/ci/probe-wine11-prefix.sh"),
            workflow.index("Start exact nightly Compose service"),
        )
        for required in (
            "for caps in standard hardened",
            "for arch in default win64 win32",
            "--rm --network none --cpus=2 --memory=3g --pids-limit=256",
            "--security-opt=no-new-privileges --user 1000:1000",
            "options+=(--cap-drop=ALL)",
            "--user 1000:1000",
            "timeout -k 5s 90s env WINEDLLOVERRIDES=mscoree,mshtml= wineboot -i",
            "timeout -k 5s 15s wine cmd /c exit 0",
            "WINE_PREFIX_PROBE caps=%s arch=%s stage=%s",
            "WINE_PREFIX_PROBE stage=target_mode_unqualified",
        ):
            self.assertIn(required, probe)
        self.assertNotIn("docker push", probe)
        self.assertNotIn("actions/upload-artifact", probe)
        self.assertNotIn("docker logs", probe)

    def test_prefix_failure_diagnostics_are_allowlisted_and_redacted(self):
        import subprocess
        import sys
        secret = "SYNTHETIC_PRIVATE_MARKER"
        classifier = str(ROOT / "scripts/ci/classify-startup-logs.py")
        for stage, expected in (
            ("wine/prefix-clone", "failed_prefix_clone"),
            ("wine/prefix-init", "failed_prefix_init"),
            ("wine/prefix-update", "failed_prefix_update"),
        ):
            payload = (
                secret + "\\n"
                + "WINEBOT_STARTUP_ERROR stage=" + stage + " rc=1\\n"
            ).replace("\\n", "\n")
            result = subprocess.run(
                [sys.executable, classifier], input=payload, text=True,
                capture_output=True, check=True, timeout=8,
            )
            self.assertEqual(result.stdout.strip(), "STARTUP_DIAGNOSTIC stage=" + expected)
            self.assertNotIn(secret, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
