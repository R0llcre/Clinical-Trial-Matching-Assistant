import jwt
from fastapi.testclient import TestClient

from app.main import app


def test_preview_token_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("CTMA_PREVIEW_TOKEN_ENABLED", raising=False)
    client = TestClient(app)
    response = client.get("/api/auth/preview-token")
    assert response.status_code == 404


def test_preview_token_enabled_issues_jwt(monkeypatch) -> None:
    monkeypatch.setenv("CTMA_PREVIEW_TOKEN_ENABLED", "1")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("CTMA_PREVIEW_TOKEN_EXPIRES_SECONDS", "3600")
    monkeypatch.setenv("CTMA_PREVIEW_TOKEN_SUB", "preview-user")
    monkeypatch.setenv("CTMA_PREVIEW_TOKEN_ROLE", "preview")

    client = TestClient(app)
    response = client.get("/api/auth/preview-token")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    token = payload["data"]["token"]
    decoded = jwt.decode(token, "test-secret", algorithms=["HS256"])
    assert decoded["sub"] == "preview-user"
    assert decoded["role"] == "preview"
    assert "exp" in decoded
