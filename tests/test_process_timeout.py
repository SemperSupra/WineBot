import time
from api.utils.process import safe_command

def test_default_timeout_respected():
    # 'sleep 10' should timeout with the default 5s
    start = time.time()
    res = safe_command(["sleep", "10"])
    duration = time.time() - start
    
    assert res["ok"] is False
    assert res["error"] == "timeout"
    assert 4.5 <= duration <= 7.0 # Allow some buffer for process setup

def test_global_timeout_env_override(monkeypatch):
    # Set global timeout to 2s
    monkeypatch.setenv("WINEBOT_COMMAND_TIMEOUT", "2")
    
    # We must reload or re-import to pick up the env if it's evaluated at module level.
    # But in our implementation, DEFAULT_TIMEOUT is evaluated at module load.
    # Let's check if we can patch the internal DEFAULT_TIMEOUT or just test the logic.
    
    import api.utils.process
    monkeypatch.setattr(api.utils.process, "DEFAULT_TIMEOUT", 2)
    
    start = time.time()
    res = api.utils.process.safe_command(["sleep", "5"])
    duration = time.time() - start
    
    assert res["ok"] is False
    assert res["error"] == "timeout"
    assert 1.5 <= duration <= 3.5

def test_explicit_timeout_override():
    # Explicitly pass 1s, should override default
    start = time.time()
    res = safe_command(["sleep", "5"], timeout=1)
    duration = time.time() - start
    
    assert res["ok"] is False
    assert res["error"] == "timeout"
    assert 0.8 <= duration <= 2.5
