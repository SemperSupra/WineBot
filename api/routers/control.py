from fastapi import APIRouter, HTTPException
import os
import time
from api.core.broker import broker
from api.core.models import GrantControlModel, UserIntentModel, ControlPolicyModeModel
from api.core.config_guard import validate_runtime_configuration
from api.core.telemetry import emit_operation_timing
from api.utils.files import (
    read_session_dir,
    resolve_session_dir,
    read_session_control_mode,
    write_session_control_mode,
    write_instance_control_mode,
)

router = APIRouter(prefix="/sessions", tags=["control"])


def _require_active_session_id(session_id: str) -> None:
    active_dir = read_session_dir()
    active_id = os.path.basename(active_dir) if active_dir else None
    if active_id != session_id:
        raise HTTPException(
            status_code=409,
            detail=f"Session '{session_id}' is not active (active session: {active_id or 'none'})",
        )


@router.get("/{session_id}/control")
def get_control_state(session_id: str):
    """Get the current interactive control state."""
    _require_active_session_id(session_id)
    state = broker.get_state()
    # Simple validation that session matches if strict
    return state


@router.post("/{session_id}/control/grant")
async def grant_control(session_id: str, data: GrantControlModel):
    """User grants control to the agent for N seconds."""
    op_started = time.perf_counter()
    _require_active_session_id(session_id)
    await broker.grant_agent(
        data.lease_seconds,
        user_ack=data.user_ack,
        challenge_token=(data.challenge_token or ""),
    )
    active_dir = read_session_dir()
    emit_operation_timing(
        active_dir,
        feature="control",
        capability="grant_renew",
        feature_set="control_input_automation",
        operation="grant_control",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="control.grant_control.latency",
    )
    return broker.get_state()


@router.post("/{session_id}/control/renew")
async def renew_control(session_id: str, data: GrantControlModel):
    """Agent requests lease renewal."""
    op_started = time.perf_counter()
    _require_active_session_id(session_id)
    await broker.renew_agent(data.lease_seconds)
    active_dir = read_session_dir()
    emit_operation_timing(
        active_dir,
        feature="control",
        capability="grant_renew",
        feature_set="control_input_automation",
        operation="renew_control",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="control.renew_control.latency",
    )
    return broker.get_state()


@router.post("/{session_id}/control/challenge")
async def issue_control_grant_challenge(session_id: str):
    """Issue a short-lived one-time challenge token for human-confirmed grants."""
    _require_active_session_id(session_id)
    challenge = await broker.issue_grant_challenge()
    return {"session_id": session_id, **challenge}


@router.post("/{session_id}/user_intent")
async def set_user_intent(session_id: str, data: UserIntentModel):
    """User sets intent (WAIT, SAFE_INTERRUPT, STOP_NOW)."""
    op_started = time.perf_counter()
    _require_active_session_id(session_id)
    await broker.set_user_intent(data.intent)
    active_dir = read_session_dir()
    emit_operation_timing(
        active_dir,
        feature="control",
        capability="user_intent",
        feature_set="control_input_automation",
        operation="set_user_intent",
        duration_ms=(time.perf_counter() - op_started) * 1000.0,
        result="ok",
        source="api",
        metric_name="control.user_intent.latency",
        tags={"intent": data.intent.value},
    )
    return broker.get_state()


@router.get("/{session_id}/control/mode")
def get_session_control_mode(session_id: str):
    target_dir = resolve_session_dir(session_id, None, None)
    return {"session_id": session_id, "mode": read_session_control_mode(target_dir)}


@router.post("/{session_id}/control/mode")
async def set_session_control_mode(
    session_id: str, data: ControlPolicyModeModel, allow_inactive: bool = False
):
    active_dir = read_session_dir()
    target_dir = resolve_session_dir(session_id, None, None)
    if not allow_inactive and active_dir != target_dir:
        raise HTTPException(
            status_code=409,
            detail="Target session is not active. Set allow_inactive=true to override.",
        )
    if (not allow_inactive) and active_dir is not None:
        runtime_mode = os.getenv("MODE", "headless")
        state = broker.get_state()
        validation_errors = validate_runtime_configuration(
            runtime_mode=runtime_mode,
            instance_lifecycle_mode=os.getenv("WINEBOT_INSTANCE_MODE", "persistent"),
            session_lifecycle_mode=os.getenv("WINEBOT_SESSION_MODE", "persistent"),
            instance_control_mode=state.instance_control_mode.value,
            session_control_mode=data.mode.value,
            build_intent=os.getenv("BUILD_INTENT", "rel"),
            allow_headless_hybrid=(
                (os.getenv("WINEBOT_ALLOW_HEADLESS_HYBRID") or "0").strip().lower()
                in {"1", "true", "yes", "on"}
            ),
        )
        if validation_errors:
            raise HTTPException(status_code=409, detail="; ".join(validation_errors))

    write_session_control_mode(target_dir, data.mode.value)
    if active_dir == target_dir:
        await broker.set_session_control_mode(data.mode)
    return {"session_id": session_id, "mode": data.mode.value}


instance_router = APIRouter(prefix="/control", tags=["control"])


@instance_router.get("/mode")
def get_instance_control_mode():
    state = broker.get_state()
    return {
        "instance_mode": state.instance_control_mode.value,
        "session_mode": state.session_control_mode.value,
        "effective_mode": state.effective_control_mode.value,
    }


@instance_router.post("/mode")
async def set_instance_control_mode(data: ControlPolicyModeModel):
    state = broker.get_state()
    validation_errors = validate_runtime_configuration(
        runtime_mode=os.getenv("MODE", "headless"),
        instance_lifecycle_mode=os.getenv("WINEBOT_INSTANCE_MODE", "persistent"),
        session_lifecycle_mode=os.getenv("WINEBOT_SESSION_MODE", "persistent"),
        instance_control_mode=data.mode.value,
        session_control_mode=state.session_control_mode.value,
        build_intent=os.getenv("BUILD_INTENT", "rel"),
        allow_headless_hybrid=(
            (os.getenv("WINEBOT_ALLOW_HEADLESS_HYBRID") or "0").strip().lower()
            in {"1", "true", "yes", "on"}
        ),
    )
    if validation_errors:
        raise HTTPException(status_code=409, detail="; ".join(validation_errors))

    write_instance_control_mode(data.mode.value)
    await broker.set_instance_control_mode(data.mode)
    state = broker.get_state()
    return {
        "instance_mode": state.instance_control_mode.value,
        "session_mode": state.session_control_mode.value,
        "effective_mode": state.effective_control_mode.value,
    }
