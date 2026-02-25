from fastapi import APIRouter
from typing import Optional
import os
import time
import platform
from api.utils.process import (
    check_binary,
    safe_command,
    safe_async_command,
    find_processes,
    pid_running,
)
from api.utils.files import (
    statvfs_info,
    read_session_dir,
    recorder_pid,
)
from api.core.recorder import recording_status
from api.core.telemetry import emit_operation_timing
from api.core.broker import broker
from api.core.config_guard import validate_runtime_configuration


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


def _process_running(name: str, pid: Optional[int]) -> bool:
    """Check if process is running by name and optional PID file."""
    if pid is not None:
        if pid_running(pid):
            return True
    return len(find_processes(name)) > 0


def _evaluate_invariants() -> dict:
    violations = []
    session_dir = read_session_dir()
    state = broker.get_state()
    runtime_mode = os.getenv("MODE", "headless")
    validation_errors = validate_runtime_configuration(
        runtime_mode=runtime_mode,
        instance_lifecycle_mode=os.getenv("WINEBOT_INSTANCE_MODE", "persistent"),
        session_lifecycle_mode=os.getenv("WINEBOT_SESSION_MODE", "persistent"),
        instance_control_mode=state.instance_control_mode.value,
        session_control_mode=state.session_control_mode.value,
        build_intent=os.getenv("BUILD_INTENT", "rel"),
        allow_headless_hybrid=(
            (os.getenv("WINEBOT_ALLOW_HEADLESS_HYBRID") or "0").strip().lower()
            in {"1", "true", "yes", "on"}
        ),
    )
    for err in validation_errors:
        violations.append({"code": "config_invalid", "detail": err})

    if session_dir and not os.path.isdir(session_dir):
        violations.append(
            {
                "code": "session_pointer_missing",
                "detail": f"WINEBOT_SESSION_DIR points to missing path: {session_dir}",
            }
        )
    if state.effective_control_mode.value == "human-only" and state.control_mode.value == "AGENT":
        violations.append(
            {
                "code": "control_human_only_violated",
                "detail": "Agent cannot be active while effective mode is human-only",
            }
        )
    if state.effective_control_mode.value == "agent-only" and state.control_mode.value != "AGENT":
        violations.append(
            {
                "code": "control_agent_only_violated",
                "detail": "Agent-only mode requires AGENT as active controller",
            }
        )
    if state.control_mode.value == "AGENT" and state.interactive and not state.lease_expiry:
        violations.append(
            {
                "code": "interactive_agent_without_lease",
                "detail": "Interactive AGENT control requires a lease expiry",
            }
        )
    return {"ok": len(violations) == 0, "violations": violations}


@router.get("")
def health_check():
    """High-level health summary."""
    op_started = time.perf_counter()
    session_dir = read_session_dir()
    x11_started = time.perf_counter()
    x11 = safe_command(["xdpyinfo"])
    emit_operation_timing(
        session_dir,
        feature="health",
        capability="subcheck",
        feature_set="runtime_foundation",
        operation="health_x11_check",
        duration_ms=(time.perf_counter() - x11_started) * 1000.0,
        result="ok" if bool(x11.get("ok")) else "error",
        source="api",
        metric_name="health.x11_check.latency",
    )
    wineprefix = os.getenv("WINEPREFIX", "/wineprefix")
    prefix_ok = os.path.isdir(wineprefix) and os.path.exists(
        os.path.join(wineprefix, "system.reg")
    )

    required_tools = ["winedbg", "gdb", "ffmpeg", "xdotool", "xdpyinfo", "Xvfb"]
    tools_started = time.perf_counter()
    missing = [t for t in required_tools if not check_binary(t)["present"]]
    emit_operation_timing(
        session_dir,
        feature="health",
        capability="subcheck",
        feature_set="runtime_foundation",
        operation="health_tools_check",
        duration_ms=(time.perf_counter() - tools_started) * 1000.0,
        result="ok" if len(missing) == 0 else "error",
        source="api",
        metric_name="health.tools_check.latency",
        tags={"missing_count": len(missing)},
    )

    storage_paths = ["/wineprefix", "/artifacts", "/tmp"]
    storage_started = time.perf_counter()
    storage = [statvfs_info(p) for p in storage_paths]
    storage_ok = all(s.get("ok") and s.get("writable", False) for s in storage)
    emit_operation_timing(
        session_dir,
        feature="health",
        capability="subcheck",
        feature_set="runtime_foundation",
        operation="health_storage_check",
        duration_ms=(time.perf_counter() - storage_started) * 1000.0,
        result="ok" if storage_ok else "error",
        source="api",
        metric_name="health.storage_check.latency",
    )

    # Security check: Detect public IP exposure with VNC
    import socket

    def is_public_ip(ip):
        if not ip or ip == "127.0.0.1":
            return False
        parts = ip.split(".")
        if len(parts) != 4:
            return True  # IPv6 or invalid
        # Private ranges: 10.x, 172.16-31.x, 192.168.x
        if parts[0] == "10":
            return False
        if parts[0] == "192" and parts[1] == "168":
            return False
        if parts[0] == "172" and 16 <= int(parts[1]) <= 31:
            return False
        return True

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        s.connect(("10.254.254.254", 1))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "unknown"

    vnc_enabled = os.getenv("ENABLE_VNC", "0") == "1"
    vnc_password = os.getenv("VNC_PASSWORD")
    security_warning = None
    if vnc_enabled:
        if is_public_ip(local_ip):
            security_warning = (
                f"VNC EXPOSED: Container has public IP {local_ip}. Use SSH tunneling."
            )
        elif not vnc_password:
            security_warning = "VNC INSECURE: VNC is enabled without a password."

    status = "ok"
    if (
        not x11.get("ok")
        or not prefix_ok
        or missing
        or not storage_ok
        or security_warning
    ):
        status = "degraded"

    invariant_report = _evaluate_invariants()
    payload = {
        "status": status,
        "x11": "connected" if x11.get("ok") else "unavailable",
        "wineprefix": "ready" if prefix_ok else "missing",
        "tools_ok": len(missing) == 0,
        "missing_tools": missing,
        "storage_ok": storage_ok,
        "security_warning": security_warning,
        "uptime_seconds": int(time.time() - START_TIME),
        "invariants_ok": invariant_report["ok"],
    }
    if not invariant_report["ok"]:
        payload["status"] = "degraded"
        payload["invariant_violations"] = invariant_report["violations"]
    emit_operation_timing(
        session_dir,
        feature="health",
        capability="aggregate",
        feature_set="runtime_foundation",
        operation="health_check",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok" if status == "ok" else "degraded",
        source="api",
        metric_name="health.check.latency",
    )
    return payload


@router.get("/invariants")
def health_invariants():
    report = _evaluate_invariants()
    return report


@router.get("/environment")
async def health_environment():
    """Deep validation of the X11 and Wine driver environment."""
    op_started = time.perf_counter()
    x11 = await safe_async_command(["xdpyinfo"])

    # Wine driver check: This verifies if winex11.drv can actually initialize
    wine_driver = await safe_async_command(["wine", "cmd", "/c", "echo Driver Check"])

    # Process checks
    wm_ok = _process_running("openbox", None)
    xvfb_ok = _process_running("Xvfb", None)
    explorer_ok = _process_running("explorer.exe", None)

    # Driver capability details
    driver_ok = wine_driver.get("ok", False)
    nodrv_detected = "nodrv_CreateWindow" in wine_driver.get("stderr", "")

    status = "ok"
    if not x11.get("ok") or not driver_ok or not xvfb_ok:
        status = "error"
    elif not wm_ok or not explorer_ok:
        status = "degraded"

    payload = {
        "status": status,
        "x11": {
            "ok": x11.get("ok"),
            "display": os.getenv("DISPLAY"),
            "xvfb_running": xvfb_ok,
            "wm_running": wm_ok,
        },
        "wine": {
            "driver_ok": driver_ok,
            "nodrv_detected": nodrv_detected,
            "explorer_running": explorer_ok,
            "stderr": wine_driver.get("stderr") if not driver_ok else None,
        },
    }
    emit_operation_timing(
        read_session_dir(),
        feature="health",
        capability="environment",
        feature_set="runtime_foundation",
        operation="health_environment",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok" if status == "ok" else status,
        source="api",
        metric_name="health.environment.latency",
    )
    return payload


@router.get("/system")
def health_system():
    """System-level health details."""
    from api.core.discovery import discovery_manager
    info = {
        "hostname": platform.node(),
        "pid": os.getpid(),
        "uptime_seconds": int(time.time() - START_TIME),
        "cpu_count": os.cpu_count(),
        "discovery": discovery_manager.status(),
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
    op_started = time.perf_counter()
    x11 = await safe_async_command(["xdpyinfo"])
    wm_ok = _process_running("openbox", None)
    active = await safe_async_command(["/automation/bin/x11.sh", "active-window"])
    payload = {
        "display": os.getenv("DISPLAY"),
        "screen": os.getenv("SCREEN"),
        "connected": x11.get("ok", False),
        "xdpyinfo_error": x11.get("error") or x11.get("stderr"),
        "window_manager": {"name": "openbox", "running": wm_ok},
        "active_window": active.get("stdout") if active.get("ok") else None,
        "active_window_error": (
            None if active.get("ok") else (active.get("error") or active.get("stderr"))
        ),
    }
    emit_operation_timing(
        read_session_dir(),
        feature="health",
        capability="x11",
        feature_set="runtime_foundation",
        operation="health_x11",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok" if bool(x11.get("ok")) else "error",
        source="api",
        metric_name="health.x11.latency",
    )
    return payload


@router.get("/windows")
async def health_windows():
    """Window list and active window details."""
    op_started = time.perf_counter()
    listing = await safe_async_command(["/automation/bin/x11.sh", "list-windows"])
    active = await safe_async_command(["/automation/bin/x11.sh", "active-window"])
    windows = []
    if listing.get("ok") and listing.get("stdout"):
        for line in listing["stdout"].splitlines():
            parts = line.strip().split(" ", 1)
            if len(parts) == 2:
                windows.append({"id": parts[0], "title": parts[1]})
    payload = {
        "count": len(windows),
        "windows": windows,
        "active_window": active.get("stdout") if active.get("ok") else None,
        "error": (
            None
            if listing.get("ok")
            else (listing.get("error") or listing.get("stderr"))
        ),
    }
    emit_operation_timing(
        read_session_dir(),
        feature="health",
        capability="windows",
        feature_set="runtime_foundation",
        operation="health_windows",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok" if bool(listing.get("ok")) else "error",
        source="api",
        metric_name="health.windows.latency",
        tags={"window_count": len(windows)},
    )
    return payload


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
        "wine_version": (
            wine_version.get("stdout") if wine_version.get("ok") else None
        ),
        "wine_version_error": (
            None
            if wine_version.get("ok")
            else (wine_version.get("error") or wine_version.get("stderr"))
        ),
        "winearch": os.getenv("WINEARCH"),
    }


@router.get("/tools")
def health_tools():
    """Presence and paths of key tooling."""
    tools = [
        "winedbg",
        "gdb",
        "ffmpeg",
        "xdotool",
        "xdpyinfo",
        "Xvfb",
        "x11vnc",
        "websockify",
        "xinput",
    ]
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
    op_started = time.perf_counter()
    session_dir = read_session_dir()
    enabled = os.getenv("WINEBOT_RECORD", "0") == "1"
    
    r_pid = recorder_pid(session_dir) if session_dir else None
    recorder_ok = _process_running("automation.recorder start", r_pid)
    
    status = recording_status(session_dir, enabled)
    payload = {
        "enabled": enabled,
        "session_dir": session_dir,
        "session_dir_exists": (os.path.isdir(session_dir) if session_dir else False),
        "recorder_running": recorder_ok,
        "recorder_pids": [str(r_pid)] if r_pid and pid_running(r_pid) else [],
        "state": status["state"],
    }
    emit_operation_timing(
        session_dir,
        feature="health",
        capability="recording",
        feature_set="recording_and_artifacts",
        operation="health_recording",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="health.recording.latency",
        tags={"recorder_running": recorder_ok, "state": status["state"]},
    )
    return payload
