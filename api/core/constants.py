from typing import Final

# Runtime modes
MODE_INTERACTIVE: Final[str] = "interactive"
MODE_HEADLESS: Final[str] = "headless"
VALID_RUNTIME_MODES: Final[set[str]] = {MODE_INTERACTIVE, MODE_HEADLESS}

# Lifecycle modes
LIFECYCLE_MODE_PERSISTENT: Final[str] = "persistent"
LIFECYCLE_MODE_ONESHOT: Final[str] = "oneshot"
VALID_LIFECYCLE_MODES: Final[set[str]] = {
    LIFECYCLE_MODE_PERSISTENT,
    LIFECYCLE_MODE_ONESHOT,
}

# Control policy modes
CONTROL_MODE_HUMAN_ONLY: Final[str] = "human-only"
CONTROL_MODE_AGENT_ONLY: Final[str] = "agent-only"
CONTROL_MODE_HYBRID: Final[str] = "hybrid"
VALID_CONTROL_POLICY_MODES: Final[set[str]] = {
    CONTROL_MODE_HUMAN_ONLY,
    CONTROL_MODE_AGENT_ONLY,
    CONTROL_MODE_HYBRID,
}

# Session states
SESSION_STATE_ACTIVE: Final[str] = "active"
SESSION_STATE_SUSPENDED: Final[str] = "suspended"
SESSION_STATE_COMPLETED: Final[str] = "completed"
VALID_SESSION_STATES: Final[set[str]] = {
    SESSION_STATE_ACTIVE,
    SESSION_STATE_SUSPENDED,
    SESSION_STATE_COMPLETED,
}
