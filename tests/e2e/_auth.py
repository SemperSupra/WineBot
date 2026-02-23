import os
import requests


API_URL = "http://winebot-interactive:8000"


def get_token() -> str:
    for token_path in ("/winebot-shared/winebot_api_token", "/tmp/winebot_api_token"):
        if os.path.exists(token_path):
            with open(token_path, "r") as f:
                return f.read().strip()
    return os.getenv("API_TOKEN", "").strip()


def auth_headers() -> dict[str, str]:
    token = get_token()
    return {"X-API-Key": token} if token else {}


def ui_url() -> str:
    token = get_token()
    if token:
        return f"{API_URL}/ui/?token={token}"
    return f"{API_URL}/ui/"


def get_session_id() -> str:
    res = requests.get(f"{API_URL}/lifecycle/status", headers=auth_headers(), timeout=10)
    res.raise_for_status()
    payload = res.json()
    session_id = payload.get("session_id")
    if not session_id:
        raise RuntimeError("No active session_id available from /lifecycle/status")
    return str(session_id)


def ensure_agent_control(lease_seconds: int = 300) -> None:
    session_id = get_session_id()
    headers = auth_headers()
    challenge_res = requests.post(
        f"{API_URL}/sessions/{session_id}/control/challenge",
        headers=headers,
        timeout=10,
    )
    challenge_res.raise_for_status()
    token = challenge_res.json().get("token")
    if not token:
        raise RuntimeError("Control challenge token was not returned")

    grant_res = requests.post(
        f"{API_URL}/sessions/{session_id}/control/grant",
        json={
            "lease_seconds": lease_seconds,
            "user_ack": True,
            "challenge_token": token,
        },
        headers=headers,
        timeout=10,
    )
    grant_res.raise_for_status()
