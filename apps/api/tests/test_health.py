from fastapi.testclient import TestClient

from app.main import app
from app.routes import health as health_module


def test_health_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "service": "api"}


def test_readyz_db_down(monkeypatch) -> None:
    def _db_down():
        return False, "db down"

    def _redis_ok():
        return True, None

    monkeypatch.setattr(health_module, "_check_postgres", _db_down)
    monkeypatch.setattr(health_module, "_check_redis", _redis_ok)

    client = TestClient(app)
    response = client.get("/readyz")

    assert response.status_code == 503
    payload = response.json()
    assert payload["ok"] is False
    assert payload["checks"]["db"]["ok"] is False
    assert payload["checks"]["redis"]["ok"] is True
