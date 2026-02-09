from fastapi.testclient import TestClient

from app.main import app
from app.routes import matching as matching_module
from app.services import rate_limiter as rate_limiter_module
from app.services.auth import create_access_token


def _auth_headers() -> dict:
    token = create_access_token(sub="test-user")
    return {"Authorization": f"Bearer {token}"}


def test_create_match_is_rate_limited(monkeypatch) -> None:
    # Force an in-memory limiter so the test does not depend on Redis.
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("MATCH_RATE_LIMIT_PER_MINUTE", "1")

    limiter = rate_limiter_module.InMemoryFixedWindowRateLimiter()
    # matching.py imports get_match_rate_limiter into its module namespace,
    # so we patch it there (not in the original module).
    monkeypatch.setattr(matching_module, "get_match_rate_limiter", lambda: limiter)

    monkeypatch.setattr(matching_module, "_get_engine", lambda: object())
    monkeypatch.setattr(matching_module, "_ensure_match_tables", lambda engine: None)
    monkeypatch.setattr(
        matching_module,
        "_load_patient_profile",
        lambda engine, patient_profile_id: {
            "demographics": {"age": 50, "sex": "female"},
            "conditions": ["diabetes"],
        },
    )
    monkeypatch.setattr(matching_module, "match_trials", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        matching_module,
        "_save_match_result",
        lambda *args, **kwargs: None,
    )

    client = TestClient(app)
    res1 = client.post(
        "/api/match",
        json={"patient_profile_id": "patient-1"},
        headers=_auth_headers(),
    )
    assert res1.status_code == 200

    res2 = client.post(
        "/api/match",
        json={"patient_profile_id": "patient-1"},
        headers=_auth_headers(),
    )
    assert res2.status_code == 429
    payload = res2.json()
    assert payload["error"]["code"] == "RATE_LIMITED"
    assert res2.headers.get("retry-after")
