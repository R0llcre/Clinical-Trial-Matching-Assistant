from fastapi.testclient import TestClient

from app.main import app
from app.routes import trials as trials_module


def test_list_trials_ok(monkeypatch) -> None:
    captured = {}
    schema_checked = {"ok": False}

    def _fake_ensure(engine):
        schema_checked["ok"] = True

    def _fake_search(
        engine,
        condition,
        status,
        phase,
        country,
        state,
        city,
        page,
        page_size,
    ):
        captured.update(
            {
                "condition": condition,
                "status": status,
                "phase": phase,
                "country": country,
                "state": state,
                "city": city,
                "page": page,
                "page_size": page_size,
            }
        )
        return (
            [
                {
                    "nct_id": "NCT123",
                    "title": "Test Trial",
                    "status": "RECRUITING",
                    "phase": "PHASE2",
                    "conditions": ["diabetes"],
                    "locations": ["Boston, MA, USA"],
                    "fetched_at": "2024-01-02T00:00:00",
                }
            ],
            1,
        )

    monkeypatch.setattr(trials_module, "_search_trials", _fake_search)
    monkeypatch.setattr(trials_module, "_get_engine", lambda: object())
    monkeypatch.setattr(trials_module, "_ensure_trials_table", _fake_ensure)

    client = TestClient(app)
    response = client.get("/api/trials?condition=diabetes&page=2&page_size=5")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["error"] is None
    assert payload["data"]["total"] == 1
    assert payload["data"]["page"] == 2
    assert payload["data"]["page_size"] == 5
    assert payload["data"]["trials"][0]["nct_id"] == "NCT123"
    assert captured["condition"] == "diabetes"
    assert captured["page"] == 2
    assert captured["page_size"] == 5
    assert schema_checked["ok"] is True


def test_list_trials_validation_error() -> None:
    client = TestClient(app)
    response = client.get("/api/trials?page=0&page_size=200")

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "VALIDATION_ERROR"


def test_get_trial_ok(monkeypatch) -> None:
    schema_checked = {"ok": False}

    def _fake_ensure(engine):
        schema_checked["ok"] = True

    def _fake_get(engine, nct_id):
        return {
            "nct_id": nct_id,
            "title": "Detail Trial",
            "summary": "Summary",
            "status": "RECRUITING",
            "phase": "PHASE1",
            "conditions": ["condition-a"],
            "eligibility_text": "Eligibility",
            "criteria": [
                {
                    "id": "rule-1",
                    "type": "INCLUSION",
                    "field": "age",
                    "operator": ">=",
                    "value": 18,
                    "evidence_text": "Adults only.",
                }
            ],
            "criteria_parser_version": "rule_v1",
            "coverage_stats": {
                "total_rules": 1,
                "unknown_rules": 0,
                "known_rules": 1,
                "failed_rules": 0,
                "coverage_ratio": 1.0,
            },
            "locations": ["City, State, Country"],
            "fetched_at": "2024-01-03T00:00:00",
        }

    monkeypatch.setattr(trials_module, "_get_trial", _fake_get)
    monkeypatch.setattr(trials_module, "_get_engine", lambda: object())
    monkeypatch.setattr(trials_module, "_ensure_trials_table", _fake_ensure)

    client = TestClient(app)
    response = client.get("/api/trials/NCT999")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["error"] is None
    assert payload["data"]["eligibility_text"] == "Eligibility"
    assert payload["data"]["criteria"][0]["id"] == "rule-1"
    assert payload["data"]["criteria_parser_version"] == "rule_v1"
    assert payload["data"]["coverage_stats"]["coverage_ratio"] == 1.0
    assert schema_checked["ok"] is True


def test_get_trial_not_found(monkeypatch) -> None:
    monkeypatch.setattr(trials_module, "_get_trial", lambda engine, nct_id: None)
    monkeypatch.setattr(trials_module, "_get_engine", lambda: object())
    monkeypatch.setattr(trials_module, "_ensure_trials_table", lambda engine: None)

    client = TestClient(app)
    response = client.get("/api/trials/NCT404")

    assert response.status_code == 404
    payload = response.json()
    assert payload["ok"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "TRIAL_NOT_FOUND"
