"""Pure synthetic tests; no graphics device or sovereign host required."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "cpu_renderer.py"
spec = importlib.util.spec_from_file_location("cpu_renderer", MODULE)
cr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cr)


class CpuRendererTests(unittest.TestCase):
    def test_profiles_are_explicit(self):
        self.assertEqual(set(cr.PROFILES), {"cpu-opengl-llvmpipe", "cpu-vulkan-lavapipe", "cpu-vulkan-swiftshader"})

    def test_opengl_clears_inherited_gpu_driver(self):
        source = {"PATH": os.environ.get("PATH", ""), "VK_DRIVER_FILES": "/host/gpu.json", "VK_ICD_FILENAMES": "/host/gpu.json"}
        output = cr.environment("cpu-opengl-llvmpipe", environ=source)
        self.assertEqual(output["GALLIUM_DRIVER"], "llvmpipe")
        self.assertEqual(output["LIBGL_ALWAYS_SOFTWARE"], "1")
        self.assertNotIn("VK_DRIVER_FILES", output)
        self.assertNotIn("VK_ICD_FILENAMES", output)
        self.assertNotIn("VK_ADD_DRIVER_FILES", output)
        self.assertIn("VK_DRIVER_FILES", source)

    def test_threads_fail_closed(self):
        for value in (0, 33, -1):
            with self.assertRaises(cr.RendererUnavailable):
                cr.environment("cpu-opengl-llvmpipe", threads=value)

    def test_missing_icd_fails_closed(self):
        with self.assertRaisesRegex(cr.RendererUnavailable, "icd_unavailable"):
            cr.environment("cpu-vulkan-lavapipe", icd="/not-an-icd.json")

    def test_icd_filename_is_family_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "gpu_icd.json"
            fake.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(cr.RendererUnavailable, "icd_unavailable"):
                cr.environment("cpu-vulkan-lavapipe", icd=str(fake))
            fake2 = Path(tmp) / "lvp_icd.x86_64.json"
            fake2.write_text("{}", encoding="utf-8")
            result = cr.environment("cpu-vulkan-lavapipe", icd=str(fake2), environ={})
            self.assertEqual(result["VK_DRIVER_FILES"], str(fake2.resolve()))
            self.assertEqual(result["VK_ICD_FILENAMES"], str(fake2.resolve()))

    def test_swiftshader_requires_explicit_icd(self):
        with patch.dict(os.environ, {"WINEBOT_SWIFTSHADER_ICD": "/nonexistent/swiftshader_icd.json"}):
            with self.assertRaises(cr.RendererUnavailable):
                cr.environment("cpu-vulkan-swiftshader")

    def test_renderer_validation_checks_device_line_not_other_text(self):
        self.assertTrue(cr.renderer_identified("cpu-opengl-llvmpipe", "OpenGL renderer string: llvmpipe (LLVM)"))
        self.assertFalse(cr.renderer_identified("cpu-opengl-llvmpipe", "OpenGL renderer string: hardware"))
        self.assertTrue(cr.renderer_identified("cpu-vulkan-lavapipe", "deviceName = llvmpipe (LLVM)"))
        self.assertFalse(cr.renderer_identified("cpu-vulkan-lavapipe", "deviceName = hardware" + chr(10) + "loader: lavapipe exists"))
        self.assertTrue(cr.renderer_identified("cpu-vulkan-swiftshader", "deviceName = SwiftShader Device"))

    def test_probe_no_raw_output(self):
        from subprocess import CompletedProcess
        with patch.object(cr, "_run", return_value=CompletedProcess(["glxinfo"], 0, "OpenGL renderer string: llvmpipe\\nHOST=private\\n", "password=secret")):
            result = cr.probe("cpu-opengl-llvmpipe", {}, 5)
            self.assertNotIn("HOST", json.dumps(result))
            self.assertNotIn("password", json.dumps(result))
            self.assertEqual(result["probe"], "passed")


    def test_cli_options_after_action_are_not_swallowed(self):
        from contextlib import redirect_stdout
        from io import StringIO
        with patch.object(cr, "environment", return_value={}), \
             patch.object(cr, "probe", return_value={"probe": "passed"}), \
             redirect_stdout(StringIO()) as output:
            self.assertEqual(cr.main(["probe", "--profile", "cpu-opengl-llvmpipe"]), 0)
        self.assertIn('"passed"', output.getvalue())

if __name__ == "__main__":
    unittest.main()
