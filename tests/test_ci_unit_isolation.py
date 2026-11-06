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

    def test_generated_api_token_is_not_ever_echoed(self):
        source = (ROOT / "scripts/init/30-start-services.sh").read_text(encoding="utf-8")
        self.assertNotIn("Generated random token: ${API_TOKEN}", source)
        self.assertIn("value not logged", source)
        self.assertIn('echo -n "$API_TOKEN" > /tmp/winebot_api_token', source)


if __name__ == "__main__":
    unittest.main()
