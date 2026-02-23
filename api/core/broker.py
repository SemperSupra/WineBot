import time
import secrets
import threading
from fastapi import HTTPException

from api.core.models import (
    ControlMode,
    UserIntent,
    AgentStatus,
    ControlState,
    ControlPolicyMode,
)
from api.utils.files import get_instance_control_mode


class InputBroker:
    def __init__(self):
        self._lock = threading.RLock()
        self.state = ControlState(
            session_id="unknown",
            interactive=False,
            control_mode=ControlMode.USER,
            user_intent=UserIntent.WAIT,
            agent_status=AgentStatus.IDLE,
            instance_control_mode=ControlPolicyMode(get_instance_control_mode()),
            session_control_mode=ControlPolicyMode.HYBRID,
            effective_control_mode=ControlPolicyMode.HYBRID,
        )
        self.last_user_activity = 0.0
        self.last_agent_activity = 0.0
        self._grant_challenge_token = None
        self._grant_challenge_expiry = 0.0

    @property
    def last_activity(self) -> float:
        return max(self.last_user_activity, self.last_agent_activity)

    def _compute_effective_mode(self) -> ControlPolicyMode:
        # Human priority is absolute if either scope requests it.
        if (
            self.state.instance_control_mode == ControlPolicyMode.HUMAN_ONLY
            or self.state.session_control_mode == ControlPolicyMode.HUMAN_ONLY
        ):
            return ControlPolicyMode.HUMAN_ONLY
        # Agent-only applies when no human-only restriction exists.
        if (
            self.state.instance_control_mode == ControlPolicyMode.AGENT_ONLY
            or self.state.session_control_mode == ControlPolicyMode.AGENT_ONLY
        ):
            return ControlPolicyMode.AGENT_ONLY
        return ControlPolicyMode.HYBRID

    async def set_instance_control_mode(self, mode: ControlPolicyMode):
        with self._lock:
            self.state.instance_control_mode = mode
            self.state.effective_control_mode = self._compute_effective_mode()
            if self.state.effective_control_mode == ControlPolicyMode.AGENT_ONLY:
                self.state.control_mode = ControlMode.AGENT
            else:
                self.state.control_mode = ControlMode.USER
                self.state.lease_expiry = None

    async def issue_grant_challenge(self, ttl_seconds: int = 30) -> dict:
        with self._lock:
            token = secrets.token_urlsafe(18)
            now = time.time()
            self._grant_challenge_token = token
            self._grant_challenge_expiry = now + max(5, ttl_seconds)
            return {"token": token, "expires_epoch": self._grant_challenge_expiry}

    async def set_session_control_mode(self, mode: ControlPolicyMode):
        with self._lock:
            self.state.session_control_mode = mode
            self.state.effective_control_mode = self._compute_effective_mode()
            if self.state.effective_control_mode == ControlPolicyMode.AGENT_ONLY:
                self.state.control_mode = ControlMode.AGENT
            else:
                self.state.control_mode = ControlMode.USER
                self.state.lease_expiry = None

    async def update_session(
        self,
        session_id: str,
        interactive: bool,
        session_control_mode: ControlPolicyMode = ControlPolicyMode.HYBRID,
    ):
        with self._lock:
            self.state.session_id = session_id
            self.state.interactive = interactive
            self.state.instance_control_mode = ControlPolicyMode(get_instance_control_mode())
            self.state.session_control_mode = session_control_mode
            self.state.effective_control_mode = self._compute_effective_mode()
            if self.state.effective_control_mode == ControlPolicyMode.AGENT_ONLY:
                self.state.control_mode = ControlMode.AGENT
                self.state.lease_expiry = None
                return
            if self.state.effective_control_mode == ControlPolicyMode.HUMAN_ONLY:
                self.state.control_mode = ControlMode.USER
                self.state.lease_expiry = None
                return
            # If not interactive, default to AGENT allowed, else USER
            if not interactive:
                self.state.control_mode = ControlMode.AGENT
            else:
                # If switching to interactive, revoke agent
                if self.state.control_mode == ControlMode.AGENT:
                    self.revoke_agent("session_became_interactive")
                self.state.control_mode = ControlMode.USER

    async def grant_agent(
        self,
        lease_seconds: int,
        user_ack: bool = False,
        challenge_token: str = "",
    ):
        with self._lock:
            if not user_ack:
                raise HTTPException(
                    status_code=403,
                    detail="User acknowledgement is required to grant agent control",
                )
            now = time.time()
            if (
                not self._grant_challenge_token
                or now > self._grant_challenge_expiry
                or challenge_token != self._grant_challenge_token
            ):
                raise HTTPException(
                    status_code=403,
                    detail="A valid one-time challenge token is required to grant control",
                )
            # One-time token semantics.
            self._grant_challenge_token = None
            self._grant_challenge_expiry = 0.0
            if self.state.effective_control_mode == ControlPolicyMode.HUMAN_ONLY:
                raise HTTPException(
                    status_code=403,
                    detail="Control mode is human-only; agent control is disabled",
                )
            if not self.state.interactive:
                return  # Always implicit in non-interactive
            self.state.control_mode = ControlMode.AGENT
            self.state.lease_expiry = time.time() + lease_seconds
            self.state.user_intent = UserIntent.WAIT

    async def renew_agent(self, lease_seconds: int):
        with self._lock:
            if self.state.control_mode != ControlMode.AGENT:
                raise HTTPException(
                    status_code=403, detail="Agent does not hold control"
                )
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
        with self._lock:
            self.last_user_activity = time.time()
            if self.state.control_mode == ControlMode.AGENT:
                self.revoke_agent("user_input_override")

    async def report_agent_activity(self):
        with self._lock:
            self.last_agent_activity = time.time()

    async def set_user_intent(self, intent: UserIntent):
        with self._lock:
            self.state.user_intent = intent
            if intent == UserIntent.STOP_NOW:
                self.revoke_agent("user_stop_now")

    async def check_access(self) -> bool:
        """Returns True if agent is allowed to execute."""
        with self._lock:
            if self.state.effective_control_mode == ControlPolicyMode.HUMAN_ONLY:
                return False
            if self.state.effective_control_mode == ControlPolicyMode.AGENT_ONLY:
                return self.state.control_mode == ControlMode.AGENT
            if not self.state.interactive:
                return True
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
        # Return a detached snapshot so callers cannot mutate shared broker state.
        with self._lock:
            return self.state.model_copy(deep=True)


# Global singleton
broker = InputBroker()
