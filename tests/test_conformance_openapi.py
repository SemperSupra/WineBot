import os
from unittest.mock import patch

from fastapi.testclient import TestClient
from openapi_spec_validator import validate

from api.server import app


client = TestClient(app)


def test_openapi_document_is_valid_31():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.get("/openapi.json")
    assert response.status_code == 200
    payload = response.json()
    assert payload["openapi"].startswith("3.1.")
    validate(payload)


def test_openapi_has_operation_ids():
    with patch.dict(os.environ, {"API_TOKEN": "test-token"}):
        response = client.get("/openapi.json")
    assert response.status_code == 200
    payload = response.json()
    for path_item in payload["paths"].values():
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            assert operation.get("operationId"), f"missing operationId in {method}"
