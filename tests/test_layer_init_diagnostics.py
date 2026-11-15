"""Zero-secret regression tests for public composite startup classification."""
import importlib.util
import io
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts/ci/classify-layer-init-logs.py"
spec = importlib.util.spec_from_file_location("layer_init", MODULE)
layer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layer)


class LayerDiagnosticsTest(unittest.TestCase):
    def test_specific_allowlisted_initialization_failures(self):
        self.assertEqual(
            layer.classify("app-seed", io.StringIO("APP_LAYER_DIAGNOSTIC stage=copy_failed\n")),
            "WINE11_LAYER_HIL service=app-seed cause=copy_failed",
        )
        self.assertEqual(
            layer.classify("state-init", io.StringIO("STATE_LAYER_DIAGNOSTIC stage=ownership_failed\n")),
            "WINE11_LAYER_HIL service=state-init cause=ownership_failed",
        )

    def test_does_not_reflect_raw_or_malformed_sensitive_output(self):
        secret = "private-token-should-not-appear"
        text = (
            f"STATE_LAYER_DIAGNOSTIC stage=ownership_failed credential={secret}\n"
            f"{secret} /home/private/mount\n"
            "APP_LAYER_DIAGNOSTIC stage=copy_failed\n"
            "STATE_LAYER_DIAGNOSTIC stage=invalid_identity extra\n"
        )
        output = layer.classify("state-init", io.StringIO(text))
        self.assertEqual(output, "WINE11_LAYER_HIL service=state-init cause=unclassified")
        self.assertNotIn(secret, output)
        self.assertNotIn("/home", output)

    def test_foreign_service_marker_is_ignored(self):
        self.assertEqual(
            layer.classify("app-seed", io.StringIO("STATE_LAYER_DIAGNOSTIC stage=ownership_failed\n")),
            "WINE11_LAYER_HIL service=app-seed cause=unclassified",
        )

    def test_hil_classifies_stderr_without_publishing_raw_logs(self):
        source = (MODULE.parents[2] / "scripts/ci/qualify-wine11-layered.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('docker logs --tail 80 "$cid" 2>&1 |', source)
        self.assertNotIn('docker logs --tail 80 "$cid" 2>/dev/null |', source)
        self.assertIn('classify-layer-init-logs.py "$service"', source)

    def test_invalid_service_refused(self):
        with self.assertRaises(ValueError):
            layer.classify("winebot-interactive", io.StringIO("APP_LAYER_DIAGNOSTIC stage=copy_failed\n"))


if __name__ == "__main__":
    unittest.main()
