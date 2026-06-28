import os
import subprocess

import httpx
import pytest


def test_environment_variables():
    """Verify essential environment variables are set."""
    assert os.environ.get("DISPLAY") is not None
    assert os.environ.get("WINEPREFIX") is not None


def test_x11_reachable():
    """Verify X11 is reachable via xdpyinfo."""
    result = subprocess.run(["xdpyinfo"], capture_output=True)
    assert result.returncode == 0, f"xdpyinfo failed: {result.stderr.decode()}"


def test_wine_driver_loading():
    """Verify Wine can load the X11 driver and run a simple command."""
    # Use WINEDEBUG to catch driver issues if they happen
    env = os.environ.copy()
    env["WINEDEBUG"] = "+winediag"
    result = subprocess.run(
        ["wine", "cmd", "/c", "echo test"], capture_output=True, env=env
    )
    assert result.returncode == 0, f"Wine command failed: {result.stderr.decode()}"
    assert "nodrv_CreateWindow" not in result.stderr.decode(), (
        "Wine driver loading failed (nodrv detected)"
    )


@pytest.mark.anyio
async def test_api_health_environment():
    """Verify the /health/environment API endpoint returns OK."""
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # Give API a moment to be reachable if just started,
        # but in our test run it should already be up.
        response = await client.get("/health/environment")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in (
            "ok",
            "degraded",
        )  # Degraded might happen if explorer is still starting
        assert data["x11"]["ok"] is True
        assert data["wine"]["driver_ok"] is True
