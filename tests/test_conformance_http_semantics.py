import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.server import app


client = TestClient(app)


def test_health_has_expected_http_headers():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.get("/health", headers={"X-API-Key": "test-token"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["x-winebot-api-version"]
    assert response.headers["x-winebot-build-version"]
    assert response.headers["x-winebot-artifact-schema-version"]
    assert response.headers["x-winebot-event-schema-version"]


def test_auth_required_for_non_ui_route_when_token_set():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.get("/health")
    assert response.status_code == 403
    assert "Invalid or missing API Token" in response.json()["detail"]


def test_ui_route_is_accessible_without_token():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.get("/ui")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_unsupported_method_returns_405():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.put("/health", headers={"X-API-Key": "test-token"})
    assert response.status_code == 405


def test_version_negotiation_returns_426_on_incompatible_min():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.get(
            "/health",
            headers={
                "X-API-Key": "test-token",
                "X-WineBot-Min-Version": "999.0",
            },
        )
    assert response.status_code == 426
    body = response.json()
    assert body["detail"] == "Upgrade Required"
    assert body["required_min_version"] == "999.0"
