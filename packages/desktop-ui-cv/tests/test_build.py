"""Verify the package builds correctly as a wheel."""

import subprocess, sys
from pathlib import Path


class TestBuild:
    """Verify the package is buildable with both sdist and wheel."""

    def test_build_wheel(self, tmp_path):
        """Build the package and verify a .whl file is produced."""
        pkg_dir = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", str(pkg_dir)],
            capture_output=True, text=True, timeout=60, cwd=pkg_dir,
        )
        assert result.returncode == 0, f"Build failed:\n{result.stderr}"

        wheels = list(pkg_dir.glob("dist/*.whl"))
        assert len(wheels) >= 1, "No wheel file produced"
        assert wheels[0].name.startswith("desktop_ui_cv"), f"Unexpected wheel name: {wheels[0].name}"
