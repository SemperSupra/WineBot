"""Smoke test for the desktop-ui-cv FastAPI server.

Verifies the server starts, responds to /health, and can process
a basic analyze request with the contour detector.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import requests


class TestServer:
    """Verify the CV sidecar server starts and responds correctly."""

    SERVER_SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "diagnostics" / "cv-sidecar-server.py"
    PORT = 18789  # non-standard to avoid conflicts
    BASE_URL = f"http://127.0.0.1:{PORT}"
    SERVER_PROC = None

    @classmethod
    def setup_class(cls):
        """Start the server as a subprocess."""
        if not cls.SERVER_SCRIPT.exists():
            raise RuntimeError(f"Server script not found: {cls.SERVER_SCRIPT}")

        cls.SERVER_PROC = subprocess.Popen(
            [sys.executable, str(cls.SERVER_SCRIPT), "--serve",
             "--host", "127.0.0.1", "--port", str(cls.PORT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait for server to be ready
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                r = requests.get(f"{cls.BASE_URL}/health", timeout=2)
                if r.status_code == 200:
                    return
            except requests.ConnectionError:
                pass
            time.sleep(0.5)

        raise RuntimeError("Server did not become healthy within 30s")

    @classmethod
    def teardown_class(cls):
        """Kill the server."""
        if cls.SERVER_PROC:
            cls.SERVER_PROC.terminate()
            cls.SERVER_PROC.wait(timeout=5)

    def test_health(self):
        """Server /health returns 200 with expected fields."""
        r = requests.get(f"{self.BASE_URL}/health", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "detector" in data
        assert "ocr_backend" in data

    def test_analyze_contour(self):
        """Analyze a test image with contour detector (no GPU needed)."""
        # Generate a small test PNG
        import io
        import cv2
        import numpy as np
        img = np.ones((200, 300, 3), dtype=np.uint8) * 240
        # Draw a rectangle (simulates a button)
        cv2.rectangle(img, (50, 80), (250, 120), (100, 100, 100), -1)
        cv2.putText(img, "OK", (140, 108), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        success, buf = cv2.imencode(".png", img)
        assert success

        r = requests.post(
            f"{self.BASE_URL}/analyze",
            files={"image": ("test.png", buf.tobytes(), "image/png")},
            params={"detector": "contour", "ocr": "tesseract"},
            timeout=15,
        )
        assert r.status_code == 200, f"Analyze failed: {r.text[:200]}"
        data = r.json()
        # Should find at least one element (the rectangle)
        assert len(data.get("elements", [])) >= 1, f"No elements found in {data}"
