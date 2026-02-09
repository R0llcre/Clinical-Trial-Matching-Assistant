from fastapi.testclient import TestClient

from app.main import app


def test_request_id_is_added_to_responses() -> None:
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    assert res.headers.get("x-request-id")


def test_request_id_is_propagated_from_client() -> None:
    client = TestClient(app)
    res = client.get("/health", headers={"X-Request-ID": "test-123"})
    assert res.status_code == 200
    assert res.headers.get("x-request-id") == "test-123"

