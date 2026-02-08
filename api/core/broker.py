import asyncio
import time
from enum import Enum
from typing import Optional
from pydantic import BaseModel
from fastapi import HTTPException

from api.core.models import ControlMode, UserIntent, AgentStatus, ControlState, GrantControlModel, UserIntentModel

class InputBroker:
    def __init__(self):
        self._lock = asyncio.Lock()
        self.state = ControlState(
            session_id="unknown",
            interactive=False,
            control_mode=ControlMode.USER,
            user_intent=UserIntent.WAIT,
            agent_status=AgentStatus.IDLE
        )
        self.last_user_activity = 0.0

    async def update_session(self, session_id: str, interactive: bool):
        async with self._lock:
            self.state.session_id = session_id
            self.state.interactive = interactive
            # If not interactive, default to AGENT allowed, else USER
            if not interactive:
                self.state.control_mode = ControlMode.AGENT
            else:
                # If switching to interactive, revoke agent
                if self.state.control_mode == ControlMode.AGENT:
                    self.revoke_agent("session_became_interactive")
                self.state.control_mode = ControlMode.USER

    async def grant_agent(self, lease_seconds: int):
        async with self._lock:
            if not self.state.interactive:
                return  # Always implicit in non-interactive
            self.state.control_mode = ControlMode.AGENT
            self.state.lease_expiry = time.time() + lease_seconds
            self.state.user_intent = UserIntent.WAIT

    async def renew_agent(self, lease_seconds: int):
        async with self._lock:
            if self.state.control_mode != ControlMode.AGENT:
                raise HTTPException(status_code=403, detail="Agent does not hold control")
            if self.state.user_intent == UserIntent.STOP_NOW:
                raise HTTPException(status_code=403, detail="User requested STOP_NOW")
            self.state.lease_expiry = time.time() + lease_seconds

    def revoke_agent(self, reason: str):
        # Sync version for internal calls
        self.state.control_mode = ControlMode.USER
        self.state.lease_expiry = None
        self.state.agent_status = AgentStatus.STOPPING
        print(f"Broker: Agent revoked ({reason})")

    async def report_user_activity(self):
        self.last_user_activity = time.time()
        if self.state.control_mode == ControlMode.AGENT:
            async with self._lock:
                self.revoke_agent("user_input_override")

    async def set_user_intent(self, intent: UserIntent):
        async with self._lock:
            self.state.user_intent = intent
            if intent == UserIntent.STOP_NOW:
                self.revoke_agent("user_stop_now")

    async def check_access(self) -> bool:
        """Returns True if agent is allowed to execute."""
        if not self.state.interactive:
            return True
        
        async with self._lock:
            if self.state.control_mode != ControlMode.AGENT:
                return False
            if self.state.lease_expiry and time.time() > self.state.lease_expiry:
                self.revoke_agent("lease_expired")
                return False
            if self.state.user_intent == UserIntent.STOP_NOW:
                self.revoke_agent("user_stop_now")
                return False
            return True

    def get_state(self) -> ControlState:
        return self.state

# Global singleton
broker = InputBroker()
