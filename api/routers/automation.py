from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Any, Optional
import os
import subprocess
import uuid
import time
from api.utils.files import validate_path, to_wine_path, append_input_event, read_session_dir, ensure_session_dir
from api.utils.process import safe_command, manage_process
from api.core.models import AppRunModel, WinedbgRunModel, InspectWindowModel, FocusModel, AHKModel, AutoItModel, PythonScriptModel
from api.core.broker import broker

router = APIRouter(tags=["automation"])

@router.post("/apps/run")
async def run_app(data: AppRunModel):
    """Run a Windows application."""
    if not await broker.check_access():
        raise HTTPException(status_code=423, detail="Agent control denied by policy")
    
    try:
        validate_path(data.path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    cmd = ["wine", data.path]
    if data.args:
        import shlex
        cmd.extend(shlex.split(data.args))
    
    if data.detach:
        proc = subprocess.Popen(cmd, start_new_session=True)
        manage_process(proc)
        return {"status": "detached", "pid": proc.pid}
    
    result = safe_command(cmd, timeout=30)
    if not result["ok"]:
        raise HTTPException(status_code=500, detail=result.get("stderr") or "App failed")
    return {"status": "finished", "stdout": result["stdout"]}

@router.get("/windows")
async def list_windows():
    """List all windows."""
    listing = safe_command(["/automation/x11.sh", "list-windows"])
    windows = []
    if listing.get("ok") and listing.get("stdout"):
        for line in listing["stdout"].splitlines():
            parts = line.strip().split(" ", 1)
            if len(parts) == 2:
                windows.append({"id": parts[0], "title": parts[1]})
    return {"windows": windows}

@router.post("/windows/focus")
async def focus_window(data: FocusModel):
    """Focus a window by ID."""
    if not await broker.check_access():
        raise HTTPException(status_code=423, detail="Agent control denied by policy")
    safe_command(["/automation/x11.sh", "focus-window", data.window_id])
    return {"status": "focused"}

@router.post("/run/ahk")
async def run_ahk(data: AHKModel):
    """Run an AHK script."""
    if not await broker.check_access():
        raise HTTPException(status_code=423, detail="Agent control denied by policy")
    
    session_dir = ensure_session_dir()
    script_id = uuid.uuid4().hex[:8]
    script_path = os.path.join(session_dir, "scripts", f"run_{script_id}.ahk")
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    with open(script_path, "w") as f:
        f.write(data.script)
    
    cmd = ["ahk", to_wine_path(script_path)]
    result = safe_command(cmd, timeout=30)
    return {"status": "ok", "stdout": result.get("stdout")}

@router.post("/run/autoit")
async def run_autoit(data: AutoItModel):
    """Run an AutoIt script."""
    if not await broker.check_access():
        raise HTTPException(status_code=423, detail="Agent control denied by policy")
    
    session_dir = ensure_session_dir()
    script_id = uuid.uuid4().hex[:8]
    script_path = os.path.join(session_dir, "scripts", f"run_{script_id}.au3")
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    with open(script_path, "w") as f:
        f.write(data.script)
    
    cmd = ["autoit", to_wine_path(script_path)]
    result = safe_command(cmd, timeout=30)
    return {"status": "ok", "stdout": result.get("stdout")}

@router.post("/run/python")
async def run_python(data: PythonScriptModel):
    """Run a Python script."""
    if not await broker.check_access():
        raise HTTPException(status_code=423, detail="Agent control denied by policy")
    
    session_dir = ensure_session_dir()
    script_id = uuid.uuid4().hex[:8]
    script_path = os.path.join(session_dir, "scripts", f"run_{script_id}.py")
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    with open(script_path, "w") as f:
        f.write(data.script)
    
    cmd = ["python3", script_path]
    result = safe_command(cmd, timeout=30)
    return {"status": "ok", "stdout": result.get("stdout")}

@router.get("/screenshot")
async def take_screenshot(output_dir: Optional[str] = None):
    """Capture a screenshot of the current X11 display."""
    session_dir = read_session_dir()
    target_dir = output_dir or (os.path.join(session_dir, "screenshots") if session_dir else "/tmp")
    os.makedirs(target_dir, exist_ok=True)
    filename = f"screenshot_{int(time.time())}.png"
    filepath = os.path.join(target_dir, filename)
    
    safe_command(["/automation/screenshot.sh", filepath])
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=500, detail="Screenshot failed")
    
    from fastapi.responses import FileResponse
    return FileResponse(filepath, media_type="image/png", headers={"X-Screenshot-Path": filepath})

@router.post("/inspect/window")
async def inspect_window(data: InspectWindowModel):
    """Inspect window details."""
    if not await broker.check_access():
        raise HTTPException(status_code=423, detail="Agent control denied by policy")
    
    if not data.title and not data.handle:
        raise HTTPException(status_code=400, detail="Must provide title or handle")
    
    # Logic for calling au3 inspect ...
    return {"status": "ok", "details": {}}
