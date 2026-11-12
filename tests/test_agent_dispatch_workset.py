"""Offline, no-credential contract for the Agent Dispatch read-only WineBot workset."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKSET = ROOT / "worksets" / "agent-dispatch.json"


def test_agent_dispatch_observation_delegation_has_no_actuation():
    data = json.loads(WORKSET.read_text(encoding="utf-8"))
    assert data["locator"] == "github-file:SemperSupra/WineBot@main:worksets/agent-dispatch.json"
    assert set(data["delegations"]) == {"winebot-observe"}
    delegation = data["delegations"]["winebot-observe"]
    assert delegation["authority"]["grants"] == ["read repository"]
    assert delegation["capabilities"]["may_delegate"] is False
    assert delegation["capabilities"]["may_build_tools"] is False
    assert delegation["capabilities"]["may_acquire_free_tools"] is False
    assert delegation["resources"][0]["limit"] == 0
    assert delegation["resources"][1]["kind"] == "workflow-dispatches"
    assert delegation["resources"][1]["limit"] == 0
    assert not set(delegation["authority"]["grants"]) & set(data["bounds"]["authority_reserved"])
    assert set(delegation["scope"]["allowed"]) <= set(data["bounds"]["scope_allowed"])
    assert "dispatch workflows" in delegation["scope"]["prohibited"]
    assert "merge or release" in delegation["scope"]["prohibited"]


def test_agent_dispatch_workset_contains_no_credential_material():
    raw = WORKSET.read_text(encoding="utf-8").lower()
    for secret_indicator in ("-----begin", "private_key", "bearer_token",
                             "api_token", "tailscale_auth", "ssh-rsa "):
        assert secret_indicator not in raw
    data = json.loads(raw)
    assert data["state"]["source_authority"]
    assert data["delegations"]["winebot-observe"]["acceptance"]["evidence_refs"]


def test_workset_has_no_deployment_identity_fields():
    data = json.loads(WORKSET.read_text(encoding="utf-8"))
    assert "client_id" not in data and "host_name" not in data
    assert data["delegations"]["winebot-observe"]["authority"]["grants"] == ["read repository"]
    assert data["delegations"]["winebot-observe"]["capabilities"]["may_delegate"] is False
