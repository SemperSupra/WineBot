from fastapi import APIRouter
from api.core.broker import broker
from api.core.models import GrantControlModel, UserIntentModel

router = APIRouter(prefix="/sessions", tags=["control"])

@router.get("/{session_id}/control")
def get_control_state(session_id: str):
    """Get the current interactive control state."""
    state = broker.get_state()
    # Simple validation that session matches if strict
    return state

@router.post("/{session_id}/control/grant")
async def grant_control(session_id: str, data: GrantControlModel):
    """User grants control to the agent for N seconds."""
    await broker.grant_agent(data.lease_seconds)
    return broker.get_state()

@router.post("/{session_id}/control/renew")
async def renew_control(session_id: str, data: GrantControlModel):
    """Agent requests lease renewal."""
    await broker.renew_agent(data.lease_seconds)
    return broker.get_state()

@router.post("/{session_id}/user_intent")
async def set_user_intent(session_id: str, data: UserIntentModel):
    """User sets intent (WAIT, SAFE_INTERRUPT, STOP_NOW)."""
    await broker.set_user_intent(data.intent)
    return broker.get_state()
