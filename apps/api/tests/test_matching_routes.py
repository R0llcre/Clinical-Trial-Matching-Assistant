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

    def _fake_save(engine, match_id, patient_profile_id, filters, top_k, results):
        captured["saved_match_id"] = match_id
        captured["saved_patient_id"] = patient_profile_id
        captured["saved_results_nct"] = results[0]["nct_id"]

    monkeypatch.setattr(matching_module, "_get_engine", lambda: object())
    monkeypatch.setattr(matching_module, "_ensure_match_tables", _fake_ensure)
    monkeypatch.setattr(matching_module, "_load_patient_profile", _fake_load_patient)
    monkeypatch.setattr(matching_module, "match_trials", _fake_match_trials)
    monkeypatch.setattr(matching_module, "_save_match_result", _fake_save)

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
    assert captured["saved_match_id"] == payload["data"]["match_id"]
    assert captured["saved_patient_id"] == "patient-1"
    assert captured["saved_results_nct"] == "NCT123"
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


def test_get_match_ok(monkeypatch) -> None:
    schema_checked = {"ok": False}

    def _fake_ensure(engine) -> None:
        schema_checked["ok"] = True

    def _fake_get_match(engine, match_id):
        return {
            "id": match_id,
            "patient_profile_id": "patient-1",
            "query_json": {"filters": {"condition": "diabetes"}, "top_k": 10},
            "results": [{"nct_id": "NCT123"}],
            "created_at": "2026-02-06T00:00:00",
        }

    monkeypatch.setattr(matching_module, "_get_engine", lambda: object())
    monkeypatch.setattr(matching_module, "_ensure_match_tables", _fake_ensure)
    monkeypatch.setattr(matching_module, "_get_match_by_id", _fake_get_match)

    client = TestClient(app)
    response = client.get("/api/matches/match-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["id"] == "match-1"
    assert payload["data"]["results"][0]["nct_id"] == "NCT123"
    assert schema_checked["ok"] is True


def test_get_match_not_found(monkeypatch) -> None:
    monkeypatch.setattr(matching_module, "_get_engine", lambda: object())
    monkeypatch.setattr(matching_module, "_ensure_match_tables", lambda engine: None)
    monkeypatch.setattr(
        matching_module, "_get_match_by_id", lambda engine, match_id: None
    )

    client = TestClient(app)
    response = client.get("/api/matches/missing")

    assert response.status_code == 404
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "NOT_FOUND"
