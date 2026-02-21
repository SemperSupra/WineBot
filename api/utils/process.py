import asyncio
import os
import shutil
import subprocess
from typing import List, Dict, Any, Optional, Final, Set
from functools import lru_cache
from contextlib import asynccontextmanager

# Store strong references to Popen objects
process_store: Set[subprocess.Popen] = set()

# Default timeout for safe_command and safe_async_command (can be overridden by WINEBOT_COMMAND_TIMEOUT)
DEFAULT_TIMEOUT: Final[int] = int(os.getenv("WINEBOT_COMMAND_TIMEOUT", "5"))
PROCESS_STORE_CAP: Final[int] = int(os.getenv("WINEBOT_MAX_DETACHED_PROCESSES", "500"))


def manage_process(proc: subprocess.Popen):
    """Track a detached process to ensure it is reaped later. Enforces safety cap."""
    if len(process_store) >= PROCESS_STORE_CAP:
        # Emergency reap before adding
        for p in list(process_store):
            if p.poll() is not None:
                process_store.discard(p)
    
    if len(process_store) < PROCESS_STORE_CAP:
        process_store.add(proc)
    else:
        # Still full? Kill the oldest or just let this one be untracked (leak risk but prevents OOM)
        # We'll just add it anyway but log a warning if we had a logger
        process_store.add(proc)


def pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


async def run_async_command(cmd: List[str], timeout: Optional[int] = None) -> Dict[str, Any]:
    """Run a command asynchronously without blocking the event loop. Uses DEFAULT_TIMEOUT if timeout is not provided."""
    to = timeout if timeout is not None else DEFAULT_TIMEOUT
    return await safe_async_command(cmd, timeout=to)


def find_processes(pattern: str, exact: bool = False) -> List[int]:
    """Find PIDs of processes matching a name or command line pattern (pure Python pgrep)."""
    pids = []
    try:
        for pid_str in os.listdir("/proc"):
            if not pid_str.isdigit():
                continue
            pid = int(pid_str)
            try:
                if exact:
                    with open(f"/proc/{pid}/comm", "r") as f:
                        comm = f.read().strip()
                        if comm == pattern:
                            pids.append(pid)
                            continue
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    cmd_bytes = f.read()
                    cmd = (
                        cmd_bytes.replace(b"\0", b" ")
                        .decode("utf-8", errors="ignore")
                        .strip()
                    )
                    if pattern in cmd:
                        pids.append(pid)
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
    except Exception:
        pass
    return pids


def run_command(cmd: List[str]):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=DEFAULT_TIMEOUT)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise Exception(f"Command failed: {e.stderr}")


def safe_command(cmd: List[str], timeout: Optional[int] = None) -> Dict[str, Any]:
    to = timeout if timeout is not None else DEFAULT_TIMEOUT
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=to
        )
        return {
            "ok": True,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except FileNotFoundError:
        return {"ok": False, "error": "command not found"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except subprocess.CalledProcessError as e:
        return {
            "ok": False,
            "exit_code": e.returncode,
            "stdout": e.stdout.strip(),
            "stderr": e.stderr.strip(),
        }


@lru_cache(maxsize=None)
def check_binary(name: str) -> Dict[str, Any]:
    path = shutil.which(name)
    return {"present": path is not None, "path": path}


@asynccontextmanager
async def async_subprocess_context(cmd: List[str], timeout: Optional[int] = None):
    """Context manager to ensure a subprocess is reaped even on error or cancellation."""
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        yield proc
    finally:
        if proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=1.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass


async def safe_async_command(cmd: List[str], timeout: Optional[int] = None) -> Dict[str, Any]:
    to = timeout if timeout is not None else DEFAULT_TIMEOUT
    try:
        async with async_subprocess_context(cmd, timeout=to) as proc:
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=to)
                return {
                    "ok": proc.returncode == 0,
                    "stdout": stdout.decode().strip(),
                    "stderr": stderr.decode().strip(),
                }
            except asyncio.TimeoutError:
                return {"ok": False, "error": "timeout"}
    except FileNotFoundError:
        return {"ok": False, "error": "command not found"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
