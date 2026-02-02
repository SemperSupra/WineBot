from fastapi import FastAPI, HTTPException, BackgroundTasks, Security, Depends
from fastapi.security import APIKeyHeader
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
import subprocess
import os
import glob
import time

app = FastAPI(title="WineBot API", description="Internal API for controlling WineBot")

# Security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_token(api_key: str = Security(api_key_header)):
    expected_token = os.getenv("API_TOKEN")
    if expected_token:
        if not api_key or api_key != expected_token:
            raise HTTPException(status_code=403, detail="Invalid or missing API Token")
    return api_key

# Apply security globally
app.router.dependencies.append(Depends(verify_token))

# Path Safety
ALLOWED_PREFIXES = ["/apps", "/wineprefix", "/tmp"]

def validate_path(path: str):
    """Ensure path is within allowed directories to prevent traversal."""
    resolved = os.path.abspath(path)
    if not any(resolved.startswith(p) for p in ALLOWED_PREFIXES):
         raise HTTPException(status_code=400, detail=f"Path not allowed. Must start with: {ALLOWED_PREFIXES}")
    return resolved

# Models
class ClickModel(BaseModel):
    x: int
    y: int

class AHKModel(BaseModel):
    script: str
    focus_title: Optional[str] = None

class AutoItModel(BaseModel):
    script: str
    focus_title: Optional[str] = None

class PythonScriptModel(BaseModel):
    script: str

class AppRunModel(BaseModel):
    path: str
    args: Optional[str] = ""
    detach: bool = False

class FocusModel(BaseModel):
    window_id: str

# Helpers
def run_command(cmd: List[str]):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Command failed: {e.stderr}")

@app.get("/health")
def health_check():
    """Check if X11 and Wine are responsive (basic check)."""
    try:
        # Check X11
        subprocess.run(["xdpyinfo"], check=True, capture_output=True)
        return {"status": "ok", "x11": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Unhealthy: {str(e)}")

@app.get("/windows")
def list_windows():
    """List visible windows."""
    try:
        output = run_command(["/automation/x11.sh", "list-windows"])
        windows = []
        if output:
            for line in output.split("\n"):
                parts = line.strip().split(" ", 1)
                if len(parts) == 2:
                    windows.append({"id": parts[0], "title": parts[1]})
        return {"windows": windows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/windows/active")
def get_active_window():
    """Get the active window ID."""
    output = run_command(["/automation/x11.sh", "active-window"])
    return {"id": output}

@app.get("/windows/search")
def search_windows(name: str):
    """Search for windows by name pattern."""
    try:
        output = run_command(["/automation/x11.sh", "search", "--name", name])
        ids = output.splitlines() if output else []
        return {"matches": ids}
    except Exception:
        # Search might fail if no windows found? xdotool usually just returns empty
        return {"matches": []}

@app.post("/windows/focus")
def focus_window(data: FocusModel):
    """Focus a window by ID."""
    run_command(["/automation/x11.sh", "focus", data.window_id])
    return {"status": "focused", "id": data.window_id}

@app.get("/apps")
def list_apps(pattern: Optional[str] = None):
    """List installed applications in the Wine prefix."""
    cmd = ["/scripts/list-installed-apps.sh"]
    if pattern:
        cmd.extend(["--pattern", pattern])
    
    try:
        output = run_command(cmd)
        apps = output.splitlines() if output else []
        return {"apps": apps}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/apps/run")
def run_app(data: AppRunModel):
    """Run a Windows application."""
    safe_path = validate_path(data.path)
    
    cmd = ["/scripts/run-app.sh", safe_path]
    if data.detach:
        cmd.append("--detach")
    
    if data.args:
        import shlex
        cmd.extend(shlex.split(data.args))

    run_command(cmd)
    return {"status": "launched", "path": safe_path}

@app.post("/run/python")
def run_python(data: PythonScriptModel):
    """Run a script using Windows Python (winpy)."""
    script_path = f"/tmp/api_script_{int(time.time())}.py"
    
    with open(script_path, "w") as f:
        f.write(data.script)
    
    # Run using winpy wrapper
    cmd = ["winpy", script_path]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return {"status": "success", "stdout": result.stdout, "stderr": result.stderr}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "exit_code": e.returncode, "stdout": e.stdout, "stderr": e.stderr}

@app.get("/screenshot")
def get_screenshot(window_id: str = "root", delay: int = 0, label: Optional[str] = None):
    """Take a screenshot and return the image."""
    filename = f"screenshot_{int(time.time())}.png"
    filepath = os.path.join("/tmp", filename)
    
    cmd = ["/automation/screenshot.sh", "--window", window_id, "--delay", str(delay)]
    if label:
        cmd.extend(["--label", label])
    cmd.append(filepath)
    
    run_command(cmd)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=500, detail="Screenshot failed to generate")
        
    return FileResponse(filepath, media_type="image/png")

@app.post("/input/mouse/click")
def click_at(data: ClickModel):
    """Click at coordinates (x, y)."""
    run_command(["/automation/x11.sh", "click-at", str(data.x), str(data.y)])
    return {"status": "clicked", "x": data.x, "y": data.y}

@app.post("/run/ahk")
def run_ahk(data: AHKModel):
    """Run an AutoHotkey script."""
    # Write script to temp file
    script_path = f"/tmp/api_script_{int(time.time())}.ahk"
    log_path = f"{script_path}.log"
    
    with open(script_path, "w") as f:
        f.write(data.script)
        
    cmd = ["/scripts/run-ahk.sh", script_path, "--log", log_path]
    if data.focus_title:
        cmd.extend(["--focus-title", data.focus_title])
        
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        # Read log
        log_content = ""
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                log_content = f.read()
        return {"status": "success", "log": log_content}
    except subprocess.CalledProcessError as e:
        # Read log even on failure
        log_content = ""
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                log_content = f.read()
        return {"status": "error", "exit_code": e.returncode, "stderr": e.stderr, "log": log_content}

@app.post("/run/autoit")
def run_autoit(data: AutoItModel):
    """Run an AutoIt script."""
    # Write script to temp file
    script_path = f"/tmp/api_script_{int(time.time())}.au3"
    log_path = f"{script_path}.log"
    
    with open(script_path, "w") as f:
        f.write(data.script)
        
    cmd = ["/scripts/run-autoit.sh", script_path, "--log", log_path]
    if data.focus_title:
        cmd.extend(["--focus-title", data.focus_title])
        
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        # Read log
        log_content = ""
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                log_content = f.read()
        return {"status": "success", "log": log_content}
    except subprocess.CalledProcessError as e:
        # Read log even on failure
        log_content = ""
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                log_content = f.read()
        return {"status": "error", "exit_code": e.returncode, "stderr": e.stderr, "log": log_content}