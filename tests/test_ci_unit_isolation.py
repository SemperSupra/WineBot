"""Source-level regression for isolated unit CI and safe startup diagnostics."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent


class CIUnitIsolationTests(unittest.TestCase):
    def test_units_do_not_start_interactive_runtime(self):
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        unit = "run --rm --no-deps test-runner scripts/ci/test.sh"
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
        self.assertIn("python3 -c 'import sys", source)
        self.assertIn('print("STARTUP_DIAGNOSTIC stage=" + label)', source)
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

    def test_generated_api_token_is_not_ever_echoed(self):
        source = (ROOT / "scripts/init/30-start-services.sh").read_text(encoding="utf-8")
        self.assertNotIn("Generated random token: ${API_TOKEN}", source)
        self.assertIn("value not logged", source)
        self.assertIn('echo -n "$API_TOKEN" > /tmp/winebot_api_token', source)


if __name__ == "__main__":
    unittest.main()
