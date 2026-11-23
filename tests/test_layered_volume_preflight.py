"""Synthetic Docker API preflight tests for distinct control-plane custody.

Runs only a fake docker CLI in a temporary directory; never creates,
mounts, prunes or inspects real host volumes.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "scripts/layers/preflight.sh"
VARIABLES = (
    "WINEBOT_APP_VOLUME", "WINEBOT_PREFIX_VOLUME", "WINEBOT_HOME_VOLUME",
    "WINEBOT_CONFIG_VOLUME", "WINEBOT_USERDATA_VOLUME", "WINEBOT_ARTIFACT_VOLUME",
    "WINEBOT_SHARED_VOLUME", "WINEBOT_CONTROL_VOLUME",
)
FAKE_DOCKER = """#!/usr/bin/env python3
import os
import sys
args = sys.argv[1:]
if len(args) < 3 or args[:2] != ["volume", "inspect"]:
    sys.exit(2)
name = args[-1]
scenario = os.environ.get("WINEBOT_TEST_SCENARIO", "ok")
if "--format" not in args:
    sys.exit(1 if scenario == "missing" and name.endswith("-control") else 0)
fmt = args[args.index("--format") + 1]
if scenario == "missing" and name.endswith("-control"):
    sys.exit(1)
if fmt == "{{.Driver}}":
    print("remote" if scenario == "driver" and name.endswith("-control") else "local")
elif fmt == "{{json .Options}}":
    print('{"device":"/synthetic/alias"}' if
          scenario == "options" and name.endswith("-control") else "null")
elif fmt == "{{.Mountpoint}}":
    if scenario == "alias" and name.endswith("-control"):
        name = name.replace("-control", "-artifacts")
    print("/synthetic/volumes/" + name)
else:
    sys.exit(2)
"""


class ExternalVolumeIdentityTest(unittest.TestCase):
    def invoke(self, scenario):
        with tempfile.TemporaryDirectory() as directory:
            mock = Path(directory) / "docker"
            mock.write_text(FAKE_DOCKER, encoding="utf-8")
            mock.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = directory + os.pathsep + env["PATH"]
            env["WINEBOT_TEST_SCENARIO"] = scenario
            for key in VARIABLES:
                suffix = key.removeprefix("WINEBOT_").removesuffix("_VOLUME").lower()
                env[key] = "winebot-fixture-" + suffix.replace("_", "-")
            env["WINEBOT_CONTROL_VOLUME"] = "winebot-fixture-control"
            env["WINEBOT_ARTIFACT_VOLUME"] = "winebot-fixture-artifacts"
            digest = "@sha256:" + "a" * 64
            env["WINEBOT_RUNTIME_IMAGE"] = "synthetic/runtime" + digest
            env["WINEBOT_APP_BUNDLE_IMAGE"] = "synthetic/apps" + digest
            return subprocess.run(
                ["bash", str(PREFLIGHT), "--check"], env=env,
                capture_output=True, text=True, check=False, timeout=5,
            )

    def test_unique_local_storage_admitted(self):
        result = self.invoke("ok")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("LAYERED_PREFLIGHT stage=ready", result.stdout)

    def test_duplicate_mountpoint_rejected(self):
        result = self.invoke("alias")
        self.assertEqual(result.returncode, 2)
        self.assertIn("stage=volume_alias_or_driver", result.stderr)
        self.assertNotIn("/synthetic/volumes", result.stderr)

    def test_bind_options_and_unknown_driver_rejected(self):
        for scenario in ("options", "driver"):
            with self.subTest(scenario=scenario):
                result = self.invoke(scenario)
                self.assertEqual(result.returncode, 2)
                self.assertIn("stage=volume_alias_or_driver", result.stderr)
                self.assertNotIn("/synthetic/alias", result.stderr)

    def test_missing_control_volume_fails_closed(self):
        result = self.invoke("missing")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stage=volume_missing", result.stderr)


if __name__ == "__main__":
    unittest.main()
