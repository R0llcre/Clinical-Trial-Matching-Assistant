from fastapi.testclient import TestClient

from app.main import app
from app.routes import matching as matching_module
from app.routes import patients as patients_module


def test_patients_requires_auth(monkeypatch) -> None:
    monkeypatch.setattr(patients_module, "_get_engine", lambda: object())
    monkeypatch.setattr(
        patients_module, "_ensure_patient_profiles_table", lambda engine: None
    )
    monkeypatch.setattr(
        patients_module, "_list_patients", lambda engine, page, page_size: ([], 0)
    )

    client = TestClient(app)
    response = client.get("/api/patients")

    assert response.status_code == 401
    payload = response.json()
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "UNAUTHORIZED"


def test_patients_reject_invalid_token(monkeypatch) -> None:
    monkeypatch.setattr(patients_module, "_get_engine", lambda: object())
    monkeypatch.setattr(
        patients_module, "_ensure_patient_profiles_table", lambda engine: None
    )
    monkeypatch.setattr(
        patients_module, "_list_patients", lambda engine, page, page_size: ([], 0)
    )

    client = TestClient(app)
    response = client.get(
        "/api/patients",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "UNAUTHORIZED"


def test_match_requires_auth(monkeypatch) -> None:
    monkeypatch.setattr(matching_module, "_get_engine", lambda: object())
    monkeypatch.setattr(matching_module, "_ensure_match_tables", lambda engine: None)

    client = TestClient(app)
    response = client.post("/api/match", json={"patient_profile_id": "patient-1"})

    assert response.status_code == 401
    payload = response.json()
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "UNAUTHORIZED"


def test_get_match_requires_auth(monkeypatch) -> None:
    monkeypatch.setattr(matching_module, "_get_engine", lambda: object())
    monkeypatch.setattr(matching_module, "_ensure_match_tables", lambda engine: None)

    client = TestClient(app)
    response = client.get("/api/matches/match-1")

    assert response.status_code == 401
    payload = response.json()
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "UNAUTHORIZED"


def test_match_reject_invalid_token(monkeypatch) -> None:
    monkeypatch.setattr(matching_module, "_get_engine", lambda: object())
    monkeypatch.setattr(matching_module, "_ensure_match_tables", lambda engine: None)

    client = TestClient(app)
    response = client.post(
        "/api/match",
        json={"patient_profile_id": "patient-1"},
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
    payload = response.json()
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "UNAUTHORIZED"
