"""Process-isolated startup qualification for default-off read-only route.

Never starts a service listener, Wine process or non-synthetic observer.
The subprocess ensures each environment is evaluated at first API import.
"""
import os
import subprocess
import sys
import unittest


ENTRYPOINT = r'''
import sys
from api.server import app
route = "/sessions/{session_id}/observations/wine-events"
matches = [item for item in app.routes if getattr(item, "path", None) == route]
should_mount = sys.argv[1] == "enabled"
if bool(matches) != should_mount:
    print("FAIL: observer_boot_mount")
    sys.exit(1)
if matches and matches[0].methods != {"GET"}:
    print("FAIL: observer_boot_methods")
    sys.exit(2)
print("PASS: observer_boot_gate")
'''


class StartupGateTests(unittest.TestCase):
    def boot(self, enabled, token):
        env = os.environ.copy()
        env["WINEBOT_WINE_EVENTS_RDTE_ENABLED"] = "1" if enabled else "0"
        env["API_TOKEN"] = token
        # No private user paths/network access, no runtime lifecycle startup.
        result = subprocess.run(
            [sys.executable, "-c", ENTRYPOINT,
             "enabled" if enabled and token else "disabled"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, "observer startup admission failed")
        self.assertIn("PASS: observer_boot_gate", result.stdout)

    def test_default_off_even_with_token(self):
        self.boot(False, "synthetic-token")

    def test_on_without_token_not_mounted(self):
        self.boot(True, "")

    def test_on_with_token_get_only(self):
        self.boot(True, "synthetic-token")


if __name__ == "__main__":
    unittest.main()
