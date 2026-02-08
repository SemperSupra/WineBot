import asyncio
import os
import shutil
import subprocess
from typing import List, Dict, Any
from functools import lru_cache

# Store strong references to Popen objects
process_store = set()

def manage_process(proc: subprocess.Popen):
    """Track a detached process to ensure it is reaped later."""
    process_store.add(proc)

def pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

async def run_async_command(cmd: List[str]) -> Dict[str, Any]:
    """Run a command asynchronously without blocking the event loop."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode().strip(),
            "stderr": stderr.decode().strip(),
            "ok": proc.returncode == 0
        }
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e), "ok": False}

def find_processes(pattern: str, exact: bool = False) -> List[int]:
    """Find PIDs of processes matching a name or command line pattern (pure Python pgrep)."""
    pids = []
    try:
        for pid_str in os.listdir('/proc'):
            if not pid_str.isdigit():
                continue
            pid = int(pid_str)
            try:
                if exact:
                    with open(f'/proc/{pid}/comm', 'r') as f:
                        comm = f.read().strip()
                        if comm == pattern:
                            pids.append(pid)
                            continue
                with open(f'/proc/{pid}/cmdline', 'rb') as f:
                    cmd_bytes = f.read()
                    cmd = cmd_bytes.replace(b'\0', b' ').decode('utf-8', errors='ignore').strip()
                    if pattern in cmd:
                        pids.append(pid)
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
    except Exception:
        pass
    return pids

def run_command(cmd: List[str]):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise Exception(f"Command failed: {e.stderr}")

def safe_command(cmd: List[str], timeout: int = 5) -> Dict[str, Any]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=timeout)
        return {"ok": True, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except FileNotFoundError:
        return {"ok": False, "error": "command not found"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "exit_code": e.returncode, "stdout": e.stdout.strip(), "stderr": e.stderr.strip()}

@lru_cache(maxsize=None)
def check_binary(name: str) -> Dict[str, Any]:
    path = shutil.which(name)
    return {"present": path is not None, "path": path}

async def safe_async_command(cmd: List[str], timeout: int = 5) -> Dict[str, Any]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return {"ok": proc.returncode == 0, "stdout": stdout.decode().strip(), "stderr": stderr.decode().strip()}
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return {"ok": False, "error": "timeout"}
    except FileNotFoundError:
        return {"ok": False, "error": "command not found"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
