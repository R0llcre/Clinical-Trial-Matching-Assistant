from fastapi.testclient import TestClient

from app.main import app
from app.routes import matching as matching_module
from app.services.auth import create_access_token

TEST_SUB = "00000000-0000-0000-0000-000000000002"


def _auth_headers() -> dict:
    token = create_access_token(sub=TEST_SUB)
    return {"Authorization": f"Bearer {token}"}


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
                    "inclusion": [
                        {
                            "rule_id": "rule-age",
                            "verdict": "PASS",
                            "evidence": "Age >= 18",
                            "rule_meta": {
                                "type": "INCLUSION",
                                "field": "age",
                                "operator": ">=",
                                "value": 18,
                                "unit": "years",
                                "time_window": None,
                                "certainty": "high",
                            },
                            "evaluation_meta": {
                                "missing_field": None,
                                "reason": None,
                                "reason_code": None,
                                "required_action": None,
                            },
                        }
                    ],
                    "exclusion": [],
                    "missing_info": [],
                },
            }
        ]

    def _fake_save(
        engine, match_id, patient_profile_id, user_id, filters, top_k, results
    ):
        captured["saved_match_id"] = match_id
        captured["saved_patient_id"] = patient_profile_id
        captured["saved_user_id"] = user_id
        captured["saved_results_nct"] = results[0]["nct_id"]

    def _fake_load_patient_with_user(engine, patient_profile_id, user_id):
        return _fake_load_patient(engine, patient_profile_id)

    monkeypatch.setattr(matching_module, "_get_engine", lambda: object())
    monkeypatch.setattr(matching_module, "_ensure_match_tables", _fake_ensure)
    monkeypatch.setattr(
        matching_module, "_load_patient_profile", _fake_load_patient_with_user
    )
    monkeypatch.setattr(matching_module, "match_trials", _fake_match_trials)
    monkeypatch.setattr(matching_module, "_save_match_result", _fake_save)

    client = TestClient(app)
    response = client.post(
        "/api/match",
        json={
            "patient_profile_id": "patient-1",
            "top_k": 5,
            "filters": {
                "status": "RECRUITING",
                "country": "United States",
                "state": "New York",
                "city": "New York",
            },
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["error"] is None
    assert isinstance(payload["data"]["match_id"], str)
    assert payload["data"]["results"][0]["nct_id"] == "NCT123"
    assert (
        payload["data"]["results"][0]["checklist"]["inclusion"][0]["rule_meta"]["field"]
        == "age"
    )
    assert (
        payload["data"]["results"][0]["checklist"]["inclusion"][0]["evaluation_meta"][
            "reason_code"
        ]
        is None
    )
    assert captured["top_k"] == 5
    assert captured["filters"]["status"] == "RECRUITING"
    assert captured["filters"]["country"] == "United States"
    assert captured["filters"]["state"] == "New York"
    assert captured["filters"]["city"] == "New York"
    assert captured["age"] == 50
    assert captured["saved_match_id"] == payload["data"]["match_id"]
    assert captured["saved_patient_id"] == "patient-1"
    assert captured["saved_user_id"] == TEST_SUB
    assert captured["saved_results_nct"] == "NCT123"
    assert schema_checked["ok"] is True


def test_create_match_validation_error() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/match",
        json={"patient_profile_id": "patient-1", "top_k": 0},
        headers=_auth_headers(),
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "VALIDATION_ERROR"


def test_create_match_validation_error_on_filter_type() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/match",
        json={
            "patient_profile_id": "patient-1",
            "filters": {"country": 1},
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert "filters.country" in payload["error"]["message"]


def test_create_match_patient_not_found(monkeypatch) -> None:
    monkeypatch.setattr(matching_module, "_get_engine", lambda: object())
    monkeypatch.setattr(matching_module, "_ensure_match_tables", lambda engine: None)
    monkeypatch.setattr(
        matching_module,
        "_load_patient_profile",
        lambda engine, patient_profile_id, user_id: None,
    )

    client = TestClient(app)
    response = client.post(
        "/api/match",
        json={"patient_profile_id": "missing"},
        headers=_auth_headers(),
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "PATIENT_NOT_FOUND"


def test_get_match_ok(monkeypatch) -> None:
    schema_checked = {"ok": False}

    def _fake_ensure(engine) -> None:
        schema_checked["ok"] = True

    def _fake_get_match(engine, match_id, user_id):
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
    response = client.get("/api/matches/match-1", headers=_auth_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["error"] is None
    assert payload["data"]["id"] == "match-1"
    assert payload["data"]["results"][0]["nct_id"] == "NCT123"
    assert schema_checked["ok"] is True


def test_get_match_not_found(monkeypatch) -> None:
    monkeypatch.setattr(matching_module, "_get_engine", lambda: object())
    monkeypatch.setattr(matching_module, "_ensure_match_tables", lambda engine: None)
    monkeypatch.setattr(
        matching_module, "_get_match_by_id", lambda engine, match_id, user_id: None
    )

    client = TestClient(app)
    response = client.get("/api/matches/missing", headers=_auth_headers())

    assert response.status_code == 404
    payload = response.json()
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "MATCH_NOT_FOUND"


def test_list_matches_ok(monkeypatch) -> None:
    schema_checked = {"ok": False}
    captured = {}

    def _fake_ensure(engine) -> None:
        schema_checked["ok"] = True

    def _fake_list(engine, *, user_id, patient_profile_id, page, page_size):
        captured["user_id"] = user_id
        captured["patient_profile_id"] = patient_profile_id
        captured["page"] = page
        captured["page_size"] = page_size
        return (
            [
                {
                    "id": "match-1",
                    "patient_profile_id": "00000000-0000-0000-0000-000000000010",
                    "query_json": {"filters": {"condition": "diabetes"}, "top_k": 10},
                    "created_at": "2026-02-06T00:00:00",
                }
            ],
            1,
        )

    monkeypatch.setattr(matching_module, "_get_engine", lambda: object())
    monkeypatch.setattr(matching_module, "_ensure_match_tables", _fake_ensure)
    monkeypatch.setattr(matching_module, "_list_matches", _fake_list)

    client = TestClient(app)
    response = client.get(
        "/api/matches?patient_profile_id=00000000-0000-0000-0000-000000000010&page=2&page_size=5",
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["error"] is None
    assert payload["data"]["total"] == 1
    assert payload["data"]["page"] == 2
    assert payload["data"]["page_size"] == 5
    assert payload["data"]["matches"][0]["id"] == "match-1"
    assert captured["user_id"] == TEST_SUB
    assert captured["patient_profile_id"] == "00000000-0000-0000-0000-000000000010"
    assert captured["page"] == 2
    assert captured["page_size"] == 5
    assert schema_checked["ok"] is True


def test_list_matches_validation_error_on_patient_profile_id(monkeypatch) -> None:
    monkeypatch.setattr(matching_module, "_get_engine", lambda: object())
    monkeypatch.setattr(matching_module, "_ensure_match_tables", lambda engine: None)

    client = TestClient(app)
    response = client.get(
        "/api/matches?patient_profile_id=not-a-uuid",
        headers=_auth_headers(),
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "VALIDATION_ERROR"
