from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.main import app
from app.routes import system as system_module


def test_dataset_meta_ok(monkeypatch) -> None:
    monkeypatch.setattr(system_module, "_get_engine", lambda: object())
    monkeypatch.setattr(system_module, "_ensure_tables", lambda engine: None)
    monkeypatch.setattr(
        system_module,
        "_build_dataset_meta",
        lambda engine: {
            "trial_total": 100,
            "latest_fetched_at": "2026-02-13T00:00:00",
            "criteria_coverage": {
                "trials_with_criteria": 75,
                "trials_without_criteria": 25,
                "coverage_ratio": 0.75,
            },
            "parser_source_breakdown": {"rule_v1": 70, "llm_v1": 5},
        },
    )

    client = TestClient(app)
    response = client.get("/api/system/dataset-meta")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["error"] is None
    assert payload["data"]["trial_total"] == 100
    assert payload["data"]["criteria_coverage"]["coverage_ratio"] == 0.75
    assert payload["data"]["parser_source_breakdown"]["rule_v1"] == 70


def test_dataset_meta_db_error(monkeypatch) -> None:
    def _raise_error() -> object:
        raise SQLAlchemyError("db down")

    monkeypatch.setattr(system_module, "_get_engine", _raise_error)

    client = TestClient(app)
    response = client.get("/api/system/dataset-meta")

    assert response.status_code == 503
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "EXTERNAL_API_ERROR"
