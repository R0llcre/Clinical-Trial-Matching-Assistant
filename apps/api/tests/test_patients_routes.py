from fastapi.testclient import TestClient

from app.main import app
from app.routes import patients as patients_module
from app.services.auth import create_access_token

TEST_SUB = "00000000-0000-0000-0000-000000000001"


def _auth_headers() -> dict:
    token = create_access_token(sub=TEST_SUB)
    return {"Authorization": f"Bearer {token}"}


def test_create_patient_ok(monkeypatch) -> None:
    schema_checked = {"ok": False}
    captured = {}

    def _fake_ensure(engine) -> None:
        schema_checked["ok"] = True

    def _fake_create(engine, profile_json, source, user_id):
        captured["profile_json"] = profile_json
        captured["source"] = source
        captured["user_id"] = user_id
        return {
            "id": "patient-1",
            "source": source,
            "profile_json": profile_json,
            "created_at": "2026-02-06T00:00:00",
            "updated_at": "2026-02-06T00:00:00",
        }

    monkeypatch.setattr(patients_module, "_get_engine", lambda: object())
    monkeypatch.setattr(
        patients_module, "_ensure_patient_profiles_table", _fake_ensure
    )
    monkeypatch.setattr(patients_module, "_create_patient", _fake_create)

    client = TestClient(app)
    response = client.post(
        "/api/patients",
        json={
            "profile_json": {"demographics": {"age": 52, "sex": "female"}},
            "source": "manual",
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["error"] is None
    assert payload["data"]["id"] == "patient-1"
    assert captured["source"] == "manual"
    assert captured["profile_json"]["demographics"]["age"] == 52
    assert captured["user_id"] == TEST_SUB
    assert schema_checked["ok"] is True


def test_create_patient_validation_error() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/patients",
        json={"profile_json": {"demographics": {"sex": "female"}}},
        headers=_auth_headers(),
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "VALIDATION_ERROR"


def test_get_patient_ok(monkeypatch) -> None:
    schema_checked = {"ok": False}

    def _fake_ensure(engine) -> None:
        schema_checked["ok"] = True

    def _fake_get(engine, patient_id, user_id):
        return {
            "id": patient_id,
            "source": "manual",
            "profile_json": {"demographics": {"age": 40, "sex": "male"}},
            "created_at": "2026-02-06T00:00:00",
            "updated_at": "2026-02-06T00:00:00",
        }

    monkeypatch.setattr(patients_module, "_get_engine", lambda: object())
    monkeypatch.setattr(
        patients_module, "_ensure_patient_profiles_table", _fake_ensure
    )
    monkeypatch.setattr(patients_module, "_get_patient", _fake_get)

    client = TestClient(app)
    response = client.get("/api/patients/patient-1", headers=_auth_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["error"] is None
    assert payload["data"]["profile_json"]["demographics"]["sex"] == "male"
    assert schema_checked["ok"] is True


def test_get_patient_not_found(monkeypatch) -> None:
    monkeypatch.setattr(patients_module, "_get_engine", lambda: object())
    monkeypatch.setattr(
        patients_module, "_ensure_patient_profiles_table", lambda engine: None
    )
    monkeypatch.setattr(
        patients_module, "_get_patient", lambda engine, patient_id, user_id: None
    )

    client = TestClient(app)
    response = client.get("/api/patients/missing", headers=_auth_headers())

    assert response.status_code == 404
    payload = response.json()
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "PATIENT_NOT_FOUND"


def test_list_patients_ok(monkeypatch) -> None:
    schema_checked = {"ok": False}
    captured = {}

    def _fake_ensure(engine) -> None:
        schema_checked["ok"] = True

    def _fake_list(engine, page, page_size, user_id):
        captured["page"] = page
        captured["page_size"] = page_size
        captured["user_id"] = user_id
        return (
            [
                {
                    "id": "patient-1",
                    "source": "manual",
                    "profile_json": {"demographics": {"age": 60, "sex": "female"}},
                    "created_at": "2026-02-06T00:00:00",
                    "updated_at": "2026-02-06T00:00:00",
                }
            ],
            1,
        )

    monkeypatch.setattr(patients_module, "_get_engine", lambda: object())
    monkeypatch.setattr(
        patients_module, "_ensure_patient_profiles_table", _fake_ensure
    )
    monkeypatch.setattr(patients_module, "_list_patients", _fake_list)

    client = TestClient(app)
    response = client.get(
        "/api/patients?page=2&page_size=5", headers=_auth_headers()
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["error"] is None
    assert payload["data"]["total"] == 1
    assert payload["data"]["page"] == 2
    assert payload["data"]["page_size"] == 5
    assert payload["data"]["patients"][0]["id"] == "patient-1"
    assert captured["page"] == 2
    assert captured["page_size"] == 5
    assert captured["user_id"] == TEST_SUB
    assert schema_checked["ok"] is True


def test_list_patients_validation_error() -> None:
    client = TestClient(app)
    response = client.get(
        "/api/patients?page=0&page_size=1000", headers=_auth_headers()
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "VALIDATION_ERROR"


def test_update_patient_ok(monkeypatch) -> None:
    schema_checked = {"ok": False}
    captured = {}

    def _fake_ensure(engine) -> None:
        schema_checked["ok"] = True

    def _fake_update(engine, patient_id, profile_json, source, user_id):
        captured["patient_id"] = patient_id
        captured["profile_json"] = profile_json
        captured["source"] = source
        captured["user_id"] = user_id
        return {
            "id": patient_id,
            "source": source,
            "profile_json": profile_json,
            "created_at": "2026-02-06T00:00:00",
            "updated_at": "2026-02-07T00:00:00",
        }

    monkeypatch.setattr(patients_module, "_get_engine", lambda: object())
    monkeypatch.setattr(
        patients_module, "_ensure_patient_profiles_table", _fake_ensure
    )
    monkeypatch.setattr(patients_module, "_update_patient", _fake_update)

    client = TestClient(app)
    response = client.put(
        "/api/patients/patient-1",
        json={
            "profile_json": {"demographics": {"age": 52, "sex": "female"}},
            "source": "manual",
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["error"] is None
    assert payload["data"]["id"] == "patient-1"
    assert captured["patient_id"] == "patient-1"
    assert captured["profile_json"]["demographics"]["age"] == 52
    assert captured["source"] == "manual"
    assert captured["user_id"] == TEST_SUB
    assert schema_checked["ok"] is True


def test_update_patient_not_found(monkeypatch) -> None:
    monkeypatch.setattr(patients_module, "_get_engine", lambda: object())
    monkeypatch.setattr(
        patients_module, "_ensure_patient_profiles_table", lambda engine: None
    )
    monkeypatch.setattr(
        patients_module,
        "_update_patient",
        lambda engine, patient_id, profile_json, source, user_id: None,
    )

    client = TestClient(app)
    response = client.put(
        "/api/patients/missing",
        json={
            "profile_json": {"demographics": {"age": 52, "sex": "female"}},
            "source": "manual",
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "PATIENT_NOT_FOUND"


def test_update_patient_validation_error() -> None:
    client = TestClient(app)
    response = client.put(
        "/api/patients/patient-1",
        json={"profile_json": {"demographics": {"sex": "female"}}},
        headers=_auth_headers(),
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "VALIDATION_ERROR"
