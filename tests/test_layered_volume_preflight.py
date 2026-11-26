"""R063: qualify release-path volume admission without touching Docker or user state."""
import json
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
    "WINEBOT_SHARED_VOLUME",
)
FAKE_DOCKER = """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
args = sys.argv[1:]
state = Path(os.environ["FIXTURE_STATE"])
log = Path(os.environ["FIXTURE_LOG"])
with log.open("a") as f:
    f.write(json.dumps(args) + "\\n")
scenario = os.environ["FIXTURE_SCENARIO"]
created = set(json.loads(state.read_text()))
name = args[-1]
if len(args) < 3 or args[0] != "volume":
    sys.exit(2)
if args[1] == "create":
    created.add(name)
    state.write_text(json.dumps(sorted(created)))
    print(name)
    sys.exit(0)
if args[1] != "inspect":
    sys.exit(2)
missing = scenario in ("missing", "create", "bad-before-create", "bad-created")
if missing and name.endswith("-app") and name not in created:
    sys.exit(1)
if "--format" not in args:
    sys.exit(0)
fmt = args[args.index("--format") + 1]
if fmt == "{{.Driver}}":
    print("remote" if scenario in ("driver", "bad-before-create")
          and name.endswith("-shared") else "local")
elif fmt == "{{json .Options}}":
    bad = ((scenario == "options" and name.endswith("-shared"))
           or (scenario == "bad-created" and name in created))
    print('{"device":"/synthetic/alias"}' if bad else "null")
elif fmt == "{{.Mountpoint}}":
    if scenario == "alias" and name.endswith("-shared"):
        name = "winebot-fixture-artifact"
    if scenario == "relative" and name.endswith("-shared"):
        print("relative")
    elif scenario == "root" and name.endswith("-shared"):
        print("/")
    elif scenario == "unavailable" and name.endswith("-shared"):
        sys.exit(2)
    else:
        print("/synthetic/volumes/" + name)
else:
    sys.exit(2)
"""


class LayeredVolumeAdmissionTests(unittest.TestCase):
    def invoke(self, scenario, operation="--check", pinned=True, duplicate=False):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            mock = work / "docker"
            mock.write_text(FAKE_DOCKER, encoding="utf-8")
            mock.chmod(0o755)
            state = work / "state.json"
            state.write_text("[]", encoding="utf-8")
            log = work / "calls.jsonl"
            log.touch()
            env = os.environ.copy()
            env["PATH"] = directory + os.pathsep + env["PATH"]
            env["FIXTURE_STATE"] = str(state)
            env["FIXTURE_LOG"] = str(log)
            env["FIXTURE_SCENARIO"] = scenario
            for key in VARIABLES:
                suffix = key.removeprefix("WINEBOT_").removesuffix("_VOLUME").lower()
                env[key] = "winebot-fixture-" + suffix
            if duplicate:
                env["WINEBOT_SHARED_VOLUME"] = env["WINEBOT_ARTIFACT_VOLUME"]
            digest = "@sha256:" + "a" * 64
            env["WINEBOT_RUNTIME_IMAGE"] = "synthetic/runtime" + digest if pinned else "latest"
            env["WINEBOT_APP_BUNDLE_IMAGE"] = "synthetic/apps" + digest if pinned else "latest"
            result = subprocess.run(
                ["bash", str(PREFLIGHT), operation], env=env, capture_output=True,
                text=True, timeout=15, check=False,
            )
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            return result, calls

    def test_unique_local_storage_admitted(self):
        result, calls = self.invoke("ok")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("stage=ready", result.stdout)
        self.assertFalse(any(c[:2] == ["volume", "create"] for c in calls))

    def test_bad_backing_storage_refused_without_leaking_paths(self):
        for scenario in ("alias", "driver", "options", "relative", "root", "unavailable"):
            with self.subTest(scenario=scenario):
                result, _ = self.invoke(scenario)
                self.assertEqual(result.returncode, 2)
                category = "volume_identity_unavailable" if scenario == "unavailable" else "volume_alias_or_driver"
                self.assertIn("stage=" + category, result.stderr)
                self.assertNotIn("/synthetic/", result.stdout + result.stderr)

    def test_create_checks_existing_storage_first(self):
        result, calls = self.invoke("bad-before-create", "--create")
        self.assertEqual(result.returncode, 2)
        self.assertIn("stage=volume_alias_or_driver", result.stderr)
        self.assertFalse(any(c[:2] == ["volume", "create"] for c in calls))

    def test_create_rechecks_daemon_result(self):
        for scenario, expected in (("create", 0), ("bad-created", 2)):
            with self.subTest(scenario=scenario):
                result, calls = self.invoke(scenario, "--create")
                self.assertEqual(result.returncode, expected)
                self.assertEqual(sum(c[:2] == ["volume", "create"] for c in calls), 1)
                if expected:
                    self.assertIn("stage=volume_alias_or_driver", result.stderr)

    def test_storage_only_is_read_only_and_not_full_admission(self):
        result, calls = self.invoke("ok", "--check-volumes", pinned=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("stage=volume_identity_ready", result.stdout)
        self.assertFalse(any(c[:2] == ["volume", "create"] for c in calls))
        result, calls = self.invoke("missing", "--check-volumes", pinned=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("stage=volume_missing", result.stderr)
        self.assertFalse(any(c[:2] == ["volume", "create"] for c in calls))
        result, calls = self.invoke("ok", pinned=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("stage=unpinned_image", result.stderr)
        self.assertFalse(calls)

    def test_duplicate_names_rejected_before_docker(self):
        result, calls = self.invoke("ok", duplicate=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("stage=invalid_volume_namespace", result.stderr)
        self.assertFalse(calls)


if __name__ == "__main__":
    unittest.main()
