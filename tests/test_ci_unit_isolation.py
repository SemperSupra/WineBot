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

    def test_generated_api_token_is_not_ever_echoed(self):
        source = (ROOT / "scripts/init/30-start-services.sh").read_text(encoding="utf-8")
        self.assertNotIn("Generated random token: ${API_TOKEN}", source)
        self.assertIn("value not logged", source)
        self.assertIn('echo -n "$API_TOKEN" > /tmp/winebot_api_token', source)


    def test_health_wait_failure_output_is_allowlisted(self):
        source = (ROOT / "scripts/ci/wait-for-container-health.sh").read_text(
            encoding="utf-8"
        )
        self.assertEqual(source.count("diagnose_health_failure"), 3)
        self.assertIn('python3 "$classifier"', source)
        self.assertIn('logs --no-color --tail 200 "$service" 2>/dev/null', source)
        self.assertNotIn('logs --tail 200 "$service" || true', source)

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

if __name__ == "__main__":
    unittest.main()
