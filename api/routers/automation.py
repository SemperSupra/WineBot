import os
import re
import shutil
import subprocess
import time
import uuid

from fastapi import APIRouter, HTTPException, Query

from api.core import wininspect
from api.core.broker import broker
from api.core.models import (
    AHKModel,
    AppRunModel,
    AutoItModel,
    ClickModel,
    FocusModel,
    InspectWindowModel,
    KeyModel,
    PythonScriptModel,
)
from api.core.telemetry import emit_operation_timing
from api.utils.config import config
from api.utils.files import (
    read_session_dir,
    to_wine_path,
    validate_path,
)
from api.utils.process import ProcessCapacityError, manage_process, safe_command

router = APIRouter(tags=["automation"])


def _wininspect_or_503() -> None:
    state = wininspect.ensure_daemon(start=True)
    if not state.get("running"):
        raise HTTPException(
            status_code=503,
            detail=str(state.get("error") or "WinInspect daemon is not available"),
        )


def _wininspect_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=f"WinInspect request failed: {exc}")


def _require_active_session() -> str:
    session_dir = read_session_dir()
    if not session_dir or not os.path.isdir(session_dir):
        raise HTTPException(
            status_code=409,
            detail="No active session. Resume or create a session before running automation.",
        )
    return session_dir


@router.post("/apps/run")
async def run_app(data: AppRunModel):
    """Run a Windows application."""
    op_started = time.perf_counter()
    if not await broker.check_access():
        raise HTTPException(status_code=423, detail="Agent control denied by policy")

    await broker.report_agent_activity()

    app_path = data.path
    # Allow naked filenames (e.g., cmd.exe, notepad.exe) or resolve non-absolute paths
    if os.path.sep not in app_path and "\\" not in app_path:
        # Naked filename, assume Wine will find it or it is in PATH
        pass
    elif not os.path.isabs(app_path):
        resolved_path = shutil.which(app_path)
        if resolved_path:
            app_path = resolved_path

    try:
        # Only validate if it looks like a path (has separators or is absolute)
        if os.path.sep in app_path or "\\" in app_path or os.path.isabs(app_path):
            validate_path(app_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Intelligently prepend 'wine'
    is_windows = any(
        app_path.lower().endswith(ext) for ext in [".exe", ".bat", ".msi", ".cmd"]
    )
    if not is_windows and not os.path.isabs(app_path):
        # If it's a naked filename, check if it's a Linux utility first
        cmd = [app_path] if shutil.which(app_path) else ["wine", app_path]
    elif is_windows:
        cmd = ["wine", app_path]
    else:
        # Absolute path, if not .exe, assume Linux
        cmd = [app_path]

    if data.args:
        import shlex

        cmd.extend(shlex.split(data.args))

    if data.detach:
        proc = subprocess.Popen(cmd, start_new_session=True)
        try:
            manage_process(proc)
        except ProcessCapacityError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        session_dir = read_session_dir()
        emit_operation_timing(
            session_dir,
            feature="automation",
            capability="app_run",
            feature_set="control_input_automation",
            operation="run_app_detach",
            duration_ms=(time.perf_counter() - op_started) * 1000.0,
            result="ok",
            source="api",
            metric_name="automation.run_app.latency",
            tags={"detach": True},
        )
        return {"status": "detached", "pid": proc.pid}

    result = safe_command(cmd, timeout=config.WINEBOT_TIMEOUT_AUTOMATION_APP_RUN_SECONDS)
    session_dir = read_session_dir()
    if not result["ok"]:
        emit_operation_timing(
            session_dir,
            feature="automation",
            capability="app_run",
            feature_set="control_input_automation",
            operation="run_app",
            duration_ms=(time.perf_counter() - op_started) * 1000.0,
            result="error",
            source="api",
            metric_name="automation.run_app.latency",
        )
        return {
            "status": "failed",
            "exit_code": result.get("exit_code"),
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", "") or result.get("error", "App failed"),
        }
    emit_operation_timing(
        session_dir,
        feature="automation",
        capability="app_run",
        feature_set="control_input_automation",
        operation="run_app",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="automation.run_app.latency",
        tags={"detach": False},
    )
    return {
        "status": "finished",
        "stdout": result["stdout"],
        "stderr": result.get("stderr", ""),
    }


@router.get("/windows")
async def list_windows():
    """List all windows."""
    listing = safe_command(["/automation/bin/x11.sh", "list-windows"])
    windows = []
    if listing.get("ok") and listing.get("stdout"):
        for line in listing["stdout"].splitlines():
            parts = line.strip().split(" ", 1)
            if len(parts) == 2:
                windows.append({"id": parts[0], "title": parts[1]})
    return {"windows": windows}


@router.get("/wininspect/capabilities")
async def wininspect_capabilities():
    """Return WinInspect runtime capabilities."""
    _wininspect_or_503()
    try:
        return {
            "ok": True,
            "capabilities": wininspect.capabilities(),
            "health": wininspect.health(),
        }
    except Exception as exc:
        raise _wininspect_error(exc)


@router.get("/wininspect/windows")
async def wininspect_windows(include_info: bool = True):
    """List top-level Windows HWNDs through WinInspect."""
    _wininspect_or_503()
    try:
        top = wininspect.list_top_windows()
        if not include_info:
            return {"ok": True, "windows": top, "count": len(top)}
        windows = []
        for item in top:
            hwnd = str(item.get("hwnd") or "").strip()
            if hwnd:
                windows.append(wininspect.window_info(hwnd))
        return {"ok": True, "windows": windows, "count": len(windows)}
    except Exception as exc:
        raise _wininspect_error(exc)


@router.get("/wininspect/window/{hwnd}")
async def wininspect_window(hwnd: str, include_tree: bool = False):
    """Inspect a single HWND through WinInspect."""
    _wininspect_or_503()
    try:
        payload = {"ok": True, "info": wininspect.window_info(hwnd)}
        if include_tree:
            payload["tree"] = wininspect.window_tree(hwnd)
        return payload
    except Exception as exc:
        raise _wininspect_error(exc)


@router.get("/wininspect/window/{hwnd}/children")
async def wininspect_children(hwnd: str):
    """List child windows of an HWND through WinInspect."""
    _wininspect_or_503()
    try:
        children = wininspect.list_children(hwnd)
        return {"ok": True, "children": children, "count": len(children)}
    except Exception as exc:
        raise _wininspect_error(exc)


@router.get("/wininspect/screen")
async def wininspect_screen():
    """Return WinInspect desktop geometry and DPI information."""
    _wininspect_or_503()
    try:
        return {"ok": True, "screen": wininspect.screen_info()}
    except Exception as exc:
        raise _wininspect_error(exc)


# ── WinInspect mutation endpoints (brokered through Input Broker) ─────────


@router.post("/wininspect/click")
async def wininspect_click(data: ClickModel):
    """Click at screen coordinates or window control via WinInspect.
    If window_id is provided, uses window.controlClick on that HWND.
    Otherwise uses input.mouseClick at absolute coordinates."""
    if not await broker.check_access():
        raise HTTPException(status_code=423, detail="Agent control denied by policy")
    await broker.report_agent_activity()
    _wininspect_or_503()
    try:
        if data.window_id:
            result = wininspect.control_click(
                hwnd=data.window_id,
                x=data.x if not data.relative else None,
                y=data.y if not data.relative else None,
                button={1: "left", 2: "right", 3: "middle"}.get(data.button, "left"),
            )
        else:
            result = wininspect.mouse_click(data.x, data.y)
        return {"ok": True, "result": result}
    except Exception as exc:
        raise _wininspect_error(exc)


@router.post("/wininspect/key")
async def wininspect_key(data: KeyModel):
    """Send keystrokes or hotkey via WinInspect.
    Single keys use input.text; composite keys (with +) use input.hotkey."""
    if not await broker.check_access():
        raise HTTPException(status_code=423, detail="Agent control denied by policy")
    await broker.report_agent_activity()
    _wininspect_or_503()
    try:
        if "+" in data.keys:
            result = wininspect.send_hotkey(data.keys)
        else:
            result = wininspect.send_text(data.keys)
        return {"ok": True, "result": result}
    except Exception as exc:
        raise _wininspect_error(exc)


@router.post("/wininspect/hotkey")
async def wininspect_hotkey(data: KeyModel):
    """Send a keyboard hotkey combination via WinInspect."""
    if not await broker.check_access():
        raise HTTPException(status_code=423, detail="Agent control denied by policy")
    await broker.report_agent_activity()
    _wininspect_or_503()
    try:
        result = wininspect.send_hotkey(data.keys)
        return {"ok": True, "result": result}
    except Exception as exc:
        raise _wininspect_error(exc)


@router.get("/wininspect/pick")
async def wininspect_pick(x: int = Query(ge=0), y: int = Query(ge=0)):
    """Return the HWND at a screen coordinate through WinInspect."""
    _wininspect_or_503()
    try:
        picked = wininspect.pick_at_point(x, y)
        hwnd = str(picked.get("hwnd") or "").strip()
        payload = {"ok": True, "picked": picked}
        if hwnd:
            payload["info"] = wininspect.window_info(hwnd)
        return payload
    except Exception as exc:
        raise _wininspect_error(exc)


@router.post("/windows/focus")
async def focus_window(data: FocusModel):
    """Focus a window by ID."""
    if not await broker.check_access():
        raise HTTPException(status_code=423, detail="Agent control denied by policy")
    safe_command(["/automation/bin/x11.sh", "focus-window", data.window_id])
    return {"status": "focused"}


@router.post("/run/ahk")
async def run_ahk(data: AHKModel):
    """Run an AHK script."""
    op_started = time.perf_counter()
    if not await broker.check_access():
        raise HTTPException(status_code=423, detail="Agent control denied by policy")

    await broker.report_agent_activity()

    session_dir = _require_active_session()
    script_id = uuid.uuid4().hex[:8]
    script_path = os.path.join(session_dir, "scripts", f"run_{script_id}.ahk")
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    with open(script_path, "w") as f:
        f.write(data.script)

    cmd = ["ahk", to_wine_path(script_path)]
    result = safe_command(cmd, timeout=config.WINEBOT_TIMEOUT_AUTOMATION_SCRIPT_SECONDS)
    emit_operation_timing(
        session_dir,
        feature="automation",
        capability="run_ahk",
        feature_set="control_input_automation",
        operation="run_ahk",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok" if bool(result.get("ok", True)) else "error",
        source="api",
        metric_name="automation.run_ahk.latency",
    )
    if not result.get("ok"):
        return {
            "status": "failed",
            "exit_code": result.get("exit_code"),
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", "") or result.get("error", "AHK failed"),
        }
    return {"status": "ok", "stdout": result.get("stdout", ""), "stderr": result.get("stderr", "")}


@router.post("/run/autoit")
async def run_autoit(data: AutoItModel):
    """Run an AutoIt script."""
    op_started = time.perf_counter()
    if not await broker.check_access():
        raise HTTPException(status_code=423, detail="Agent control denied by policy")

    await broker.report_agent_activity()

    session_dir = _require_active_session()
    script_id = uuid.uuid4().hex[:8]
    script_path = os.path.join(session_dir, "scripts", f"run_{script_id}.au3")
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    with open(script_path, "w") as f:
        f.write(data.script)

    cmd = ["autoit", to_wine_path(script_path)]
    result = safe_command(cmd, timeout=config.WINEBOT_TIMEOUT_AUTOMATION_SCRIPT_SECONDS)
    emit_operation_timing(
        session_dir,
        feature="automation",
        capability="run_autoit",
        feature_set="control_input_automation",
        operation="run_autoit",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok" if bool(result.get("ok", True)) else "error",
        source="api",
        metric_name="automation.run_autoit.latency",
    )
    if not result.get("ok"):
        return {
            "status": "failed",
            "exit_code": result.get("exit_code"),
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", "") or result.get("error", "AutoIt failed"),
        }
    return {"status": "ok", "stdout": result.get("stdout", ""), "stderr": result.get("stderr", "")}


@router.post("/run/python")
async def run_python(data: PythonScriptModel):
    """Run a Python script."""
    op_started = time.perf_counter()
    if not await broker.check_access():
        raise HTTPException(status_code=423, detail="Agent control denied by policy")

    await broker.report_agent_activity()

    session_dir = _require_active_session()
    script_id = uuid.uuid4().hex[:8]
    script_path = os.path.join(session_dir, "scripts", f"run_{script_id}.py")
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    with open(script_path, "w") as f:
        f.write(data.script)

    cmd = ["python3", script_path]
    result = safe_command(cmd, timeout=config.WINEBOT_TIMEOUT_AUTOMATION_SCRIPT_SECONDS)
    emit_operation_timing(
        session_dir,
        feature="automation",
        capability="run_python",
        feature_set="control_input_automation",
        operation="run_python",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok" if bool(result.get("ok", True)) else "error",
        source="api",
        metric_name="automation.run_python.latency",
    )
    if not result.get("ok"):
        return {
            "status": "failed",
            "exit_code": result.get("exit_code"),
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", "") or result.get("error", "Python script failed"),
        }
    return {"status": "ok", "stdout": result.get("stdout", ""), "stderr": result.get("stderr", "")}


@router.get("/screenshot")
async def take_screenshot(output_dir: str | None = None):
    """Capture a screenshot of the current X11 display."""
    session_dir = read_session_dir()
    target_dir = output_dir or (
        os.path.join(session_dir, "screenshots") if session_dir else "/tmp"
    )
    os.makedirs(target_dir, exist_ok=True)

    # Correctness: Enforce screenshot cap per session
    if session_dir and target_dir.startswith(session_dir):
        max_shots = int(os.getenv("WINEBOT_MAX_SCREENSHOTS_PER_SESSION", "1000"))
        try:
            count = len([f for f in os.listdir(target_dir) if f.endswith(".png")])
            if count >= max_shots:
                raise HTTPException(
                    status_code=429,
                    detail=f"Screenshot cap ({max_shots}) reached for this session."
                )
        except OSError:
            pass

    filename = f"screenshot_{int(time.time())}.png"
    filepath = os.path.join(target_dir, filename)

    capture = safe_command(["/automation/bin/screenshot.sh", filepath])
    if (not capture.get("ok")) or (not os.path.exists(filepath)):
        # Retry once for transient X11/ImageMagick race conditions under load.
        time.sleep(0.3)
        capture = safe_command(["/automation/bin/screenshot.sh", filepath])

    if not os.path.exists(filepath):
        raise HTTPException(status_code=500, detail="Screenshot failed")

    from fastapi.responses import FileResponse

    return FileResponse(
        filepath, media_type="image/png", headers={"X-Screenshot-Path": filepath}
    )


@router.post("/inspect/window")
async def inspect_window(data: InspectWindowModel):
    """Inspect window details."""
    if not await broker.check_access():
        raise HTTPException(status_code=423, detail="Agent control denied by policy")

    if not data.title and not data.handle:
        raise HTTPException(status_code=400, detail="Must provide title or handle")

    _wininspect_or_503()
    try:
        if data.list_only:
            windows = wininspect.list_top_windows()
            return {
                "status": "ok",
                "backend": "wininspect",
                "windows": windows,
                "count": len(windows),
            }

        hwnd = data.handle
        matches = []
        if not hwnd and data.title:
            matches = wininspect.find_windows(title_regex=re.escape(data.title))
            if not matches and data.include_empty:
                matches = wininspect.find_windows(title_regex=data.title)
            if matches:
                hwnd = str(matches[0].get("hwnd") or "").strip()

        if not hwnd:
            raise HTTPException(status_code=404, detail="Window not found")

        info = wininspect.window_info(hwnd)
        payload: dict[str, object] = {
            "status": "ok",
            "backend": "wininspect",
            "handle": hwnd,
            "details": info,
        }
        if matches:
            payload["matches"] = matches[: data.max_controls]
        if data.include_controls:
            payload["controls"] = wininspect.window_tree(hwnd)
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise _wininspect_error(exc)
