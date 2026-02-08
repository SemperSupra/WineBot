from fastapi import APIRouter
import os
import time
import platform
from api.utils.process import check_binary, safe_command, safe_async_command, find_processes, pid_running
from api.utils.files import statvfs_info, read_session_dir, session_id_from_dir, input_trace_pid
from api.core.recorder import recording_status, RecorderState
from api.core.broker import broker

router = APIRouter(prefix="/health", tags=["health"])

START_TIME = time.time()

def meminfo_summary() -> dict:
    data = {}
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    data["mem_total_kb"] = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    data["mem_available_kb"] = int(line.split()[1])
    except Exception:
        pass
    return data

@router.get("")
def health_check():
    """High-level health summary."""
    x11 = safe_command(["xdpyinfo"])
    wineprefix = os.getenv("WINEPREFIX", "/wineprefix")
    prefix_ok = os.path.isdir(wineprefix) and os.path.exists(os.path.join(wineprefix, "system.reg"))

    required_tools = ["winedbg", "gdb", "ffmpeg", "xdotool", "wmctrl", "xdpyinfo", "Xvfb"]
    missing = [t for t in required_tools if not check_binary(t)["present"]]

    storage_paths = ["/wineprefix", "/artifacts", "/tmp"]
    storage = [statvfs_info(p) for p in storage_paths]
    storage_ok = all(s.get("ok") and s.get("writable", False) for s in storage)

    status = "ok"
    if not x11.get("ok") or not prefix_ok or missing or not storage_ok:
        status = "degraded"

    return {
        "status": status,
        "x11": "connected" if x11.get("ok") else "unavailable",
        "wineprefix": "ready" if prefix_ok else "missing",
        "tools_ok": len(missing) == 0,
        "missing_tools": missing,
        "storage_ok": storage_ok,
        "uptime_seconds": int(time.time() - START_TIME),
    }

@router.get("/environment")
async def health_environment():
    """Deep validation of the X11 and Wine driver environment."""
    x11 = await safe_async_command(["xdpyinfo"])
    
    # Wine driver check: This verifies if winex11.drv can actually initialize
    wine_driver = await safe_async_command(["wine", "cmd", "/c", "echo Driver Check"])
    
    # Process checks
    wm_pids = find_processes("openbox", exact=True)
    xvfb_pids = find_processes("Xvfb", exact=True)
    explorer_pids = find_processes("explorer.exe")
    
    # Driver capability details
    driver_ok = wine_driver.get("ok", False)
    nodrv_detected = "nodrv_CreateWindow" in wine_driver.get("stderr", "")
    
    status = "ok"
    if not x11.get("ok") or not driver_ok or len(xvfb_pids) == 0:
        status = "error"
    elif len(wm_pids) == 0 or len(explorer_pids) == 0:
        status = "degraded"

    return {
        "status": status,
        "x11": {
            "ok": x11.get("ok"),
            "display": os.getenv("DISPLAY"),
            "xvfb_running": len(xvfb_pids) > 0,
            "wm_running": len(wm_pids) > 0,
        },
        "wine": {
            "driver_ok": driver_ok,
            "nodrv_detected": nodrv_detected,
            "explorer_running": len(explorer_pids) > 0,
            "stderr": wine_driver.get("stderr") if not driver_ok else None,
        }
    }

@router.get("/system")
def health_system():
    """System-level health details."""
    info = {
        "hostname": platform.node(),
        "pid": os.getpid(),
        "uptime_seconds": int(time.time() - START_TIME),
        "cpu_count": os.cpu_count(),
    }
    try:
        info["loadavg"] = os.getloadavg()
    except OSError:
        pass
    info.update(meminfo_summary())
    return info

@router.get("/x11")
async def health_x11():
    """X11 health details."""
    x11 = await safe_async_command(["xdpyinfo"])
    wm_pids = find_processes("openbox", exact=True)
    active = await safe_async_command(["/automation/x11.sh", "active-window"])
    return {
        "display": os.getenv("DISPLAY"),
        "screen": os.getenv("SCREEN"),
        "connected": x11.get("ok", False),
        "xdpyinfo_error": x11.get("error") or x11.get("stderr"),
        "window_manager": {"name": "openbox", "running": len(wm_pids) > 0},
        "active_window": active.get("stdout") if active.get("ok") else None,
        "active_window_error": None if active.get("ok") else (active.get("error") or active.get("stderr")),
    }

@router.get("/windows")
async def health_windows():
    """Window list and active window details."""
    listing = await safe_async_command(["/automation/x11.sh", "list-windows"])
    active = await safe_async_command(["/automation/x11.sh", "active-window"])
    windows = []
    if listing.get("ok") and listing.get("stdout"):
        for line in listing["stdout"].splitlines():
            parts = line.strip().split(" ", 1)
            if len(parts) == 2:
                windows.append({"id": parts[0], "title": parts[1]})
    return {
        "count": len(windows),
        "windows": windows,
        "active_window": active.get("stdout") if active.get("ok") else None,
        "error": None if listing.get("ok") else (listing.get("error") or listing.get("stderr")),
    }

@router.get("/wine")
def health_wine():
    """Wine prefix and binary details."""
    wineprefix = os.getenv("WINEPREFIX", "/wineprefix")
    prefix_exists = os.path.isdir(wineprefix)
    system_reg = os.path.join(wineprefix, "system.reg")
    system_reg_exists = os.path.exists(system_reg)
    owner_uid = None
    try:
        owner_uid = os.stat(wineprefix).st_uid
    except Exception:
        pass
    wine_version = safe_command(["wine", "--version"])
    return {
        "wineprefix": wineprefix,
        "prefix_exists": prefix_exists,
        "system_reg_exists": system_reg_exists,
        "prefix_owner_uid": owner_uid,
        "current_uid": os.getuid(),
        "wine_version": wine_version.get("stdout") if wine_version.get("ok") else None,
        "wine_version_error": None if wine_version.get("ok") else (wine_version.get("error") or wine_version.get("stderr")),
        "winearch": os.getenv("WINEARCH"),
    }

@router.get("/tools")
def health_tools():
    """Presence and paths of key tooling."""
    tools = ["winedbg", "gdb", "ffmpeg", "xdotool", "wmctrl", "xdpyinfo", "Xvfb", "x11vnc", "websockify", "xinput"]
    details = {name: check_binary(name) for name in tools}
    missing = [name for name, info in details.items() if not info["present"]]
    return {"ok": len(missing) == 0, "missing": missing, "tools": details}

@router.get("/storage")
def health_storage():
    """Disk space and writeability for key paths."""
    paths = ["/wineprefix", "/artifacts", "/tmp"]
    details = [statvfs_info(p) for p in paths]
    ok = all(d.get("ok") and d.get("writable", False) for d in details)
    return {"ok": ok, "paths": details}

@router.get("/recording")
async def health_recording():
    """Recorder status and current session."""
    session_dir = read_session_dir()
    recorder_pids = find_processes("automation.recorder start")
    enabled = os.getenv("WINEBOT_RECORD", "0") == "1"
    status = recording_status(session_dir, enabled)
    return {
        "enabled": enabled,
        "session_dir": session_dir,
        "session_dir_exists": os.path.isdir(session_dir) if session_dir else False,
        "recorder_running": len(recorder_pids) > 0,
        "recorder_pids": [str(p) for p in recorder_pids],
        "state": status["state"],
    }
