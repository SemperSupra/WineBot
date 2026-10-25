"""Opt-in, read-only Wine event observation over the existing WineBot API.

No HTTP methods to start observers, ingest events, mutate windows, or grant
session control. The existing API token must be nonblank, even though legacy
WineBot endpoints may intentionally allow missing token in local deployments.
"""
import hmac
import os

from fastapi import APIRouter, Header, HTTPException, Query

from api.core.broker import broker
from api.core.wine_events_rdte import registry
from api.utils.config import config
from api.utils.files import read_session_dir

router = APIRouter(tags=["wine-event-observation-rdte"])


def _admit(session_id: str, provided: str | None) -> None:
    if os.getenv("WINEBOT_WINE_EVENTS_RDTE_ENABLED", "0") != "1":
        raise HTTPException(status_code=404, detail="capability_disabled")
    expected = (os.getenv("API_TOKEN") or config.API_TOKEN or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="observer_auth_unconfigured")
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="observer_auth_required")

    active_dir = read_session_dir()
    active_id = os.path.basename(active_dir.rstrip(os.sep)) if active_dir else None
    registry.session_changed(active_id)
    if active_id is None:
        raise HTTPException(status_code=409, detail="no_active_session")
    if not session_id or session_id != active_id:
        raise HTTPException(status_code=404, detail="session_not_found")

    # Do not expose a stale stream during session handover.
    state = broker.get_state()
    if getattr(state, "session_id", None) != session_id:
        raise HTTPException(status_code=409, detail="session_handover")


@router.get("/sessions/{session_id}/observations/wine-events")
def observe_wine_events(
    session_id: str,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=64, ge=1, le=128),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _admit(session_id, x_api_key)
    result = registry.observe(session_id, after=after, limit=limit)
    # Re-check active identity before returning in case of handover.
    active = read_session_dir()
    now = os.path.basename(active.rstrip(os.sep)) if active else None
    if now != session_id or getattr(broker.get_state(), "session_id", None) != session_id:
        registry.session_changed(now)
        raise HTTPException(status_code=409, detail="session_handover")
    return {"schema": "winebot.wine.event.v1", **result}


@router.get("/sessions/{session_id}/observations/wine-events/capabilities")
def wine_event_capabilities(
    session_id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    _admit(session_id, x_api_key)
    state = registry.observe(session_id, after=0, limit=1)["state"]
    return {
        "schema": "winebot.wine.event.v1",
        "read_only": True,
        "collector": "ready" if state in ("ready", "history_gap") else "unavailable",
        "features": ["bounded_events", "cursor", "history_gap", "session_handover"],
        "uia": "unqualified",
        "cv": "unqualified",
    }
