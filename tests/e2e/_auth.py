import os
import time
import requests


API_URL = "http://winebot-interactive:8000"


def get_token() -> str:
    env_token = os.getenv("API_TOKEN", "").strip()
    if env_token:
        return env_token
    for token_path in ("/winebot-shared/winebot_api_token", "/tmp/winebot_api_token"):
        if os.path.exists(token_path):
            with open(token_path, "r") as f:
                return f.read().strip()
    return ""


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


def ensure_openbox_running(stable_checks: int = 3, check_interval_s: float = 0.5) -> None:
    headers = auth_headers()
    def _critical_processes_ok() -> bool:
        try:
            status = requests.get(f"{API_URL}/lifecycle/status", headers=headers, timeout=10)
            status.raise_for_status()
            processes = status.json().get("processes", {})
            return bool(processes.get("openbox", {}).get("ok")) and bool(
                processes.get("xvfb", {}).get("ok")
            )
        except Exception:
            return False

    stable = 0
    for _ in range(max(stable_checks, 1)):
        if _critical_processes_ok():
            stable += 1
            time.sleep(check_interval_s)
        else:
            stable = 0
            break
    if stable >= max(stable_checks, 1):
        return

    ensure_agent_control()
    requests.post(
        f"{API_URL}/apps/run",
        json={"path": "openbox", "detach": True},
        headers=headers,
        timeout=10,
    )
    stable = 0
    for _ in range(40):
        if _critical_processes_ok():
            stable += 1
            if stable >= max(stable_checks, 1):
                return
        else:
            stable = 0
        time.sleep(check_interval_s)

    raise RuntimeError("Openbox/Xvfb did not become healthy and stable before timeout")
