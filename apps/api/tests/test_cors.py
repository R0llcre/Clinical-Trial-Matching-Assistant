from fastapi.testclient import TestClient

from app.main import app


def test_preflight_options_on_protected_route_is_allowed() -> None:
    client = TestClient(app)
    response = client.options(
        "/api/patients",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_unauthorized_response_includes_cors_headers() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/patients",
        headers={"Origin": "http://localhost:3000", "Content-Type": "application/json"},
        json={},
    )

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "x-request-id" in response.headers
