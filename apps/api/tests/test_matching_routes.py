from fastapi.testclient import TestClient

from app.main import app
from app.routes import matching as matching_module


def test_create_match_ok(monkeypatch) -> None:
    schema_checked = {"ok": False}
    captured = {}

    def _fake_ensure(engine) -> None:
        schema_checked["ok"] = True

    def _fake_load_patient(engine, patient_profile_id):
        return {
            "demographics": {"age": 50, "sex": "female"},
            "conditions": ["diabetes"],
        }

    def _fake_match_trials(engine, patient_profile, filters, top_k):
        captured["filters"] = filters
        captured["top_k"] = top_k
        captured["age"] = patient_profile["demographics"]["age"]
        return [
            {
                "nct_id": "NCT123",
                "score": 1.3,
                "certainty": 0.66,
                "checklist": {
                    "inclusion": [],
                    "exclusion": [],
                    "missing_info": [],
                },
            }
        ]

    monkeypatch.setattr(matching_module, "_get_engine", lambda: object())
    monkeypatch.setattr(matching_module, "_ensure_match_tables", _fake_ensure)
    monkeypatch.setattr(matching_module, "_load_patient_profile", _fake_load_patient)
    monkeypatch.setattr(matching_module, "match_trials", _fake_match_trials)

    client = TestClient(app)
    response = client.post(
        "/api/match",
        json={
            "patient_profile_id": "patient-1",
            "top_k": 5,
            "filters": {"status": "RECRUITING"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert isinstance(payload["data"]["match_id"], str)
    assert payload["data"]["results"][0]["nct_id"] == "NCT123"
    assert captured["top_k"] == 5
    assert captured["filters"]["status"] == "RECRUITING"
    assert captured["age"] == 50
    assert schema_checked["ok"] is True


def test_create_match_validation_error() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/match",
        json={"patient_profile_id": "patient-1", "top_k": 0},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "VALIDATION_ERROR"


def test_create_match_patient_not_found(monkeypatch) -> None:
    monkeypatch.setattr(matching_module, "_get_engine", lambda: object())
    monkeypatch.setattr(matching_module, "_ensure_match_tables", lambda engine: None)
    monkeypatch.setattr(
        matching_module,
        "_load_patient_profile",
        lambda engine, patient_profile_id: None,
    )

    client = TestClient(app)
    response = client.post("/api/match", json={"patient_profile_id": "missing"})

    assert response.status_code == 404
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "PATIENT_NOT_FOUND"
