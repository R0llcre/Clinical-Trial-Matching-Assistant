from fastapi.testclient import TestClient

from app.main import app
from app.routes import matching as matching_module
from app.services.auth import create_access_token
from app.services.observability import reset_ops_metrics


def _auth_headers() -> dict:
    token = create_access_token(sub="observability-test-user")
    return {"Authorization": f"Bearer {token}"}


def test_ops_metrics_defaults_zero() -> None:
    reset_ops_metrics()
    client = TestClient(app)

    response = client.get("/api/ops/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["match"]["requests_total"] == 0
    assert payload["match"]["success_total"] == 0
    assert payload["match"]["failure_total"] == 0
    assert payload["match"]["avg_duration_ms"] == 0.0
    assert payload["updated_at"] is None


def test_ops_metrics_track_match_success_and_failure(monkeypatch) -> None:
    reset_ops_metrics()
    monkeypatch.setenv("MATCH_RATE_LIMIT_PER_MINUTE", "0")
    monkeypatch.setattr(matching_module, "_get_engine", lambda: object())
    monkeypatch.setattr(matching_module, "_ensure_match_tables", lambda engine: None)
    monkeypatch.setattr(
        matching_module,
        "_load_patient_profile",
        lambda engine, patient_profile_id: {"demographics": {"age": 40}},
    )
    monkeypatch.setattr(
        matching_module,
        "match_trials",
        lambda engine, patient_profile, filters, top_k: [],
    )
    monkeypatch.setattr(
        matching_module,
        "_save_match_result",
        lambda engine, match_id, patient_profile_id, filters, top_k, results: None,
    )

    client = TestClient(app)

    ok_response = client.post(
        "/api/match",
        json={"patient_profile_id": "patient-1"},
        headers=_auth_headers(),
    )
    assert ok_response.status_code == 200

    invalid_response = client.post(
        "/api/match",
        json={"patient_profile_id": "patient-1", "top_k": 0},
        headers=_auth_headers(),
    )
    assert invalid_response.status_code == 400

    metrics_response = client.get("/api/ops/metrics")
    assert metrics_response.status_code == 200
    payload = metrics_response.json()
    assert payload["match"]["requests_total"] == 2
    assert payload["match"]["success_total"] == 1
    assert payload["match"]["failure_total"] == 1
    assert payload["match"]["avg_duration_ms"] >= 0.0
    assert isinstance(payload["updated_at"], str)
