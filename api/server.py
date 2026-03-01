from fastapi import FastAPI, Request, HTTPException, Security, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from fastapi.responses import FileResponse, StreamingResponse
from contextlib import asynccontextmanager
import os
import asyncio
import hmac
from typing import Optional

try:
    import uvloop

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

from api.routers import health, lifecycle, input, recording, control, automation
from api.utils.files import (
    read_session_dir,
    read_session_control_mode,
    append_lifecycle_event,
    cleanup_old_sessions,
    ensure_user_profile,
    link_wine_user_dir,
    write_instance_state,
)
from api.utils.process import reap_finished_tracked_processes
from api.core.discovery import discovery_manager
from api.core.versioning import (
    API_VERSION,
    ARTIFACT_SCHEMA_VERSION,
    EVENT_SCHEMA_VERSION,
)
from api.utils.config import config
from api.utils.logging import logger
from api.core.monitor import inactivity_monitor_task
from api.core.broker import broker
from api.core.models import ControlPolicyMode
from api.core.config_guard import validate_current_environment
from api.core.session_context import set_current_session_dir, reset_current_session_dir


NOVNC_CORE_DIR = "/usr/share/novnc/core"
NOVNC_VENDOR_DIR = "/usr/share/novnc/vendor"
_follow_stream_semaphore = asyncio.Semaphore(
    max(1, int(config.WINEBOT_MAX_LOG_FOLLOW_STREAMS))
)


def _load_version():
    try:
        with open("/VERSION", "r") as f:
            return f.read().strip()
    except Exception:
        return "v0.9.0-dev"


VERSION = _load_version()


async def resource_monitor_task():
    """Background task to reap zombies and monitor disk usage."""
    cleanup_counter = 0
    logger.info("Resource monitor task started.")
    monitor_interval = max(1, int(config.WINEBOT_RESOURCE_MONITOR_INTERVAL_SECONDS))
    cleanup_interval = max(1, int(config.WINEBOT_SESSION_CLEANUP_INTERVAL_SECONDS))
    while True:
        # Reap completed detached children under lock.
        reap_finished_tracked_processes()

        # Periodic session cleanup (every 60 seconds)
        cleanup_counter += monitor_interval
        if cleanup_counter >= cleanup_interval:
            cleanup_counter = 0
            try:
                cleanup_old_sessions(
                    max_sessions=config.WINEBOT_MAX_SESSIONS,
                    ttl_days=config.WINEBOT_SESSION_TTL_DAYS,
                )
            except Exception as e:
                logger.error(f"Session cleanup failed: {e}")

        await asyncio.sleep(monitor_interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    validation_errors = validate_current_environment()
    if validation_errors:
        joined = "; ".join(validation_errors)
        raise RuntimeError(f"Configuration admission rejected: {joined}")

    write_instance_state("running", reason="api_lifespan_start")
    session_dir = read_session_dir()
    append_lifecycle_event(
        session_dir, "api_started", "API server started", source="api"
    )

    # Ensure wine user link is active
    if session_dir and os.path.isdir(session_dir):
        user_dir = os.path.join(session_dir, "user")
        os.makedirs(user_dir, exist_ok=True)
        ensure_user_profile(user_dir)
        link_wine_user_dir(user_dir)
        interactive = os.getenv("MODE", "headless") == "interactive"
        session_control_mode = ControlPolicyMode(read_session_control_mode(session_dir))
        validation_errors = validate_current_environment(session_control_mode.value)
        if validation_errors:
            joined = "; ".join(validation_errors)
            raise RuntimeError(f"Configuration admission rejected: {joined}")
        await broker.update_session(
            os.path.basename(session_dir),
            interactive,
            session_control_mode=session_control_mode,
        )

    # Start Discovery
    try:
        session_id = os.path.basename(session_dir) if session_dir else "none"
        discovery_manager.start(session_id)
    except Exception as e:
        logger.warning(f"Discovery initialization failed: {e}")

    # Start background monitor
    monitor = asyncio.create_task(resource_monitor_task())
    inactivity_monitor = asyncio.create_task(inactivity_monitor_task())

    try:
        yield
    finally:
        write_instance_state("stopping", reason="api_lifespan_stop")
        monitor.cancel()
        inactivity_monitor.cancel()
        discovery_manager.stop()
        session_dir = read_session_dir()
        append_lifecycle_event(
            session_dir, "api_stopped", "API server stopping", source="api"
        )


app = FastAPI(
    title="WineBot API",
    description="Internal API for controlling WineBot",
    lifespan=lifespan,
)


@app.middleware("http")
async def add_security_and_version_headers(request: Request, call_next):
    active_session_dir = read_session_dir()
    session_token = set_current_session_dir(active_session_dir)
    if active_session_dir and not os.getenv("PYTEST_CURRENT_TEST"):
        try:
            broker_state = broker.get_state()
            broker_session_id = (
                broker_state.session_id if hasattr(broker_state, "session_id") else None
            )
            active_session_id = os.path.basename(active_session_dir)
            if broker_session_id != active_session_id:
                interactive = os.getenv("MODE", "headless") == "interactive"
                try:
                    session_control_mode = ControlPolicyMode(
                        read_session_control_mode(active_session_dir)
                    )
                except Exception:
                    session_control_mode = ControlPolicyMode.HYBRID
                await broker.update_session(
                    active_session_id,
                    interactive,
                    session_control_mode=session_control_mode,
                )
        except Exception:
            # Keep request path resilient; control state will self-heal on next request.
            pass
    # Phase 1: Version Negotiation
    min_version = request.headers.get("X-WineBot-Min-Version")
    if min_version:
        try:
            if float(min_version) > float(API_VERSION):
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=426,
                    content={
                        "detail": "Upgrade Required",
                        "current_api_version": API_VERSION,
                        "required_min_version": min_version
                    }
                )
        except ValueError:
            pass

    try:
        response = await call_next(request)
    finally:
        reset_current_session_dir(session_token)
    # Version Headers
    response.headers["X-WineBot-API-Version"] = API_VERSION
    response.headers["X-WineBot-Build-Version"] = VERSION
    response.headers["X-WineBot-Artifact-Schema-Version"] = ARTIFACT_SCHEMA_VERSION
    response.headers["X-WineBot-Event-Schema-Version"] = EVENT_SCHEMA_VERSION
    
    # Security Hardening Headers
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    # Content Security Policy (Optimized for noVNC requirement of WebSockets)
    # Allow self, but also allow data: for icons/images and blob: for noVNC worker
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self' ws: wss:; "
        "worker-src 'self' blob:; "
        "frame-ancestors 'none';"
    )
    response.headers["Content-Security-Policy"] = csp
    
    return response


if os.path.isdir(NOVNC_CORE_DIR):
    app.mount("/ui/core", StaticFiles(directory=NOVNC_CORE_DIR), name="novnc-core")
if os.path.isdir(NOVNC_VENDOR_DIR):
    app.mount(
        "/ui/vendor", StaticFiles(directory=NOVNC_VENDOR_DIR), name="novnc-vendor"
    )

# Security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_token_logic(request: Request, api_key: str = Security(api_key_header)):
    path = request.url.path
    if path == "/" or path.startswith("/ui"):
        return api_key

    expected_token = (os.getenv("API_TOKEN") or config.API_TOKEN or "").strip()
    if expected_token:
        provided_token = (api_key or "").strip()
        if not provided_token or not hmac.compare_digest(provided_token, expected_token):
            raise HTTPException(status_code=403, detail="Invalid or missing API Token")
    return api_key


app.router.dependencies.append(Depends(verify_token_logic))

# Include Routers
app.include_router(health.router)
app.include_router(lifecycle.router)
app.include_router(input.router)
app.include_router(recording.router)
app.include_router(control.router)
app.include_router(control.instance_router)
app.include_router(automation.router)


@app.get("/version")
def get_version():
    return {
        "version": VERSION,
        "api_version": API_VERSION,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "event_schema_version": EVENT_SCHEMA_VERSION,
    }


@app.get("/handshake")
def handshake():
    """Initial handshake for agents to negotiate versions and capabilities."""
    return {
        "status": "ready",
        "build_version": VERSION,
        "api_version": API_VERSION,
        "schema_versions": {
            "artifact": ARTIFACT_SCHEMA_VERSION,
            "event": EVENT_SCHEMA_VERSION,
        },
        "capabilities": [
            "inactivity_monitor",
            "atomic_shutdown",
            "efficient_tail_read"
        ]
    }


@app.get("/")
@app.get("/ui/")
@app.get("/ui")
def dashboard():
    UI_DIR = os.path.join(os.path.dirname(__file__), "ui")
    UI_INDEX = os.path.join(UI_DIR, "index.html")
    if not os.path.exists(UI_INDEX):
        raise HTTPException(status_code=404, detail="Dashboard not available")

    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    return FileResponse(UI_INDEX, media_type="text/html", headers=headers)


@app.get("/logs/tail")
async def tail_logs(
    source: str = "api",
    lines: int = 50,
    follow: bool = False,
    session_id: Optional[str] = None
):
    """Tail specific log sources (api, recorder, ahk, x11)."""
    from api.utils.files import resolve_session_dir, read_session_dir
    if lines < 1:
        raise HTTPException(status_code=400, detail="lines must be >= 1")
    if lines > config.WINEBOT_MAX_LOG_TAIL_LINES:
        raise HTTPException(
            status_code=400,
            detail=f"lines must be <= {config.WINEBOT_MAX_LOG_TAIL_LINES}",
        )
    
    # Logic to map source to file path
    target_dir = resolve_session_dir(session_id, None, None) if session_id else read_session_dir()
    if not target_dir:
        raise HTTPException(status_code=404, detail="Session not found")
        
    log_map = {
        "api": os.path.join(target_dir, "logs", "api.log"),
        "recorder": os.path.join(target_dir, "logs", "recorder.log"),
        "ahk": os.path.join(target_dir, "logs", "ahk_trace.log"),
        "x11": os.path.join(target_dir, "logs", "input_trace.log"),
        "lifecycle": os.path.join(target_dir, "logs", "lifecycle.jsonl")
    }
    
    path = log_map.get(source)
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Log source '{source}' not found")

    if not follow:
        from api.utils.files import read_file_tail_lines
        content = read_file_tail_lines(path, limit=lines)
        return {"source": source, "lines": content}

    try:
        await asyncio.wait_for(
            _follow_stream_semaphore.acquire(),
            timeout=max(0.001, float(config.WINEBOT_LOG_FOLLOW_ACQUIRE_TIMEOUT_SECONDS)),
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=429,
            detail=(
                "Too many active log follow streams. "
                f"Try again later (max={config.WINEBOT_MAX_LOG_FOLLOW_STREAMS})."
            ),
        )

    async def log_generator():
        from api.utils.files import follow_file

        idle_timeout = max(1, int(config.WINEBOT_LOG_FOLLOW_IDLE_TIMEOUT_SECONDS))
        stream = follow_file(path)
        try:
            while True:
                try:
                    line = await asyncio.wait_for(stream.__anext__(), timeout=idle_timeout)
                except asyncio.TimeoutError:
                    break
                except StopAsyncIteration:
                    break
                yield f"{line}\n"
        finally:
            await stream.aclose()
            _follow_stream_semaphore.release()

    return StreamingResponse(log_generator(), media_type="text/plain")
