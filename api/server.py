from fastapi import FastAPI, Request, HTTPException, Security, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.security import APIKeyHeader
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os
import asyncio

try:
    import uvloop

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass

from api.routers import health, lifecycle, input, recording, control, automation
from api.utils.files import (
    read_session_dir,
    append_lifecycle_event,
    cleanup_old_sessions,
    link_wine_user_dir,
)
from api.utils.process import process_store
from api.core.discovery import discovery_manager
from api.core.versioning import (
    API_VERSION,
    ARTIFACT_SCHEMA_VERSION,
    EVENT_SCHEMA_VERSION,
)


NOVNC_CORE_DIR = "/usr/share/novnc/core"
NOVNC_VENDOR_DIR = "/usr/share/novnc/vendor"


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
    while True:
        # Reap zombie processes
        for proc in list(process_store):
            if proc.poll() is not None:
                process_store.discard(proc)

        # Periodic session cleanup (every 60 seconds)
        cleanup_counter += 5
        if cleanup_counter >= 60:
            cleanup_counter = 0
            try:
                max_s = os.getenv("WINEBOT_MAX_SESSIONS")
                ttl_d = os.getenv("WINEBOT_SESSION_TTL_DAYS")
                cleanup_old_sessions(
                    max_sessions=int(max_s) if max_s else None,
                    ttl_days=int(ttl_d) if ttl_d else None,
                )
            except Exception:
                pass

        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    session_dir = read_session_dir()
    append_lifecycle_event(
        session_dir, "api_started", "API server started", source="api"
    )

    # Ensure wine user link is active
    if session_dir and os.path.isdir(session_dir):
        user_dir = os.path.join(session_dir, "user")
        os.makedirs(user_dir, exist_ok=True)
        link_wine_user_dir(user_dir)

    # Start Discovery
    try:
        session_id = os.path.basename(session_dir) if session_dir else "none"
        discovery_manager.start(session_id)
    except Exception as e:
        # We don't want to crash the whole API if discovery fails, unless it's a singleton conflict
        # DiscoveryManager.start() raises SystemExit for singleton conflict
        print(f"--> Discovery initialization failed: {e}")

    # Start background monitor
    monitor = asyncio.create_task(resource_monitor_task())

    try:
        yield
    finally:
        monitor.cancel()
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
async def add_version_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-WineBot-API-Version"] = API_VERSION
    response.headers["X-WineBot-Build-Version"] = VERSION
    response.headers["X-WineBot-Artifact-Schema-Version"] = ARTIFACT_SCHEMA_VERSION
    response.headers["X-WineBot-Event-Schema-Version"] = EVENT_SCHEMA_VERSION
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
    if request.url.path.startswith("/ui"):
        return api_key
    expected_token = os.getenv("API_TOKEN")
    if expected_token:
        if not api_key or api_key != expected_token:
            raise HTTPException(status_code=403, detail="Invalid or missing API Token")
    return api_key


app.router.dependencies.append(Depends(verify_token_logic))

# Include Routers
app.include_router(health.router)
app.include_router(lifecycle.router)
app.include_router(input.router)
app.include_router(recording.router)
app.include_router(control.router)
app.include_router(automation.router)


@app.get("/version")
def get_version():
    return {
        "version": VERSION,
        "api_version": API_VERSION,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "event_schema_version": EVENT_SCHEMA_VERSION,
    }


@app.get("/ui")
def dashboard_redirect():
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/ui/")


@app.get("/ui/")
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
