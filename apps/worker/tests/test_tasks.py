import datetime as dt

import pytest

import tasks
from tasks import (
    _build_query_term,
    _compute_coverage_stats,
    _extract_trial,
    parse_trial,
    sync_trials,
)


class _FakeConn:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def test_build_query_term_quotes_spaces() -> None:
    assert _build_query_term("breast cancer") == 'AREA[ConditionSearch]"breast cancer"'
    assert _build_query_term("diabetes") == "AREA[ConditionSearch]diabetes"


def test_extract_trial_maps_fields() -> None:
    study = {
        "protocolSection": {
            "identificationModule": {
                "nctId": "NCT123",
                "briefTitle": "Test Trial",
            },
            "statusModule": {
                "overallStatus": "RECRUITING",
                "lastUpdateSubmitDate": "2024-02-03",
            },
            "designModule": {"phases": ["PHASE2"]},
            "conditionsModule": {"conditions": ["condition-a"]},
            "eligibilityModule": {"eligibilityCriteria": "Adults only"},
            "contactsLocationsModule": {"locations": [{"country": "USA"}]},
        }
    }

    trial = _extract_trial(study)

    assert trial["nct_id"] == "NCT123"
    assert trial["title"] == "Test Trial"
    assert trial["status"] == "RECRUITING"
    assert trial["phase"] == "PHASE2"
    assert trial["conditions"] == ["condition-a"]
    assert trial["eligibility_text"] == "Adults only"
    assert trial["locations_json"] == [{"country": "USA"}]
    assert isinstance(trial["data_timestamp"], dt.datetime)


def test_sync_trials_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL not set"):
        sync_trials(condition="cancer")


def test_parse_trial_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")

    fake_conn = _FakeConn()
    captured = {}
    logs = []

    monkeypatch.setattr(tasks.psycopg, "connect", lambda _: fake_conn)
    monkeypatch.setattr(tasks, "_ensure_tables", lambda conn: None)
    monkeypatch.setattr(
        tasks,
        "_fetch_trial_for_parse",
        lambda conn, nct_id: {
            "id": "trial-uuid",
            "nct_id": nct_id,
            "eligibility_text": "Inclusion: Adults aged 18 years or older.",
        },
    )
    monkeypatch.setattr(
        tasks,
        "parse_criteria_v1",
        lambda text: [
            {
                "id": "rule-1",
                "type": "INCLUSION",
                "field": "age",
                "operator": ">=",
                "value": 18,
                "unit": "years",
                "time_window": None,
                "certainty": "high",
                "evidence_text": "Adults aged 18 years or older.",
                "source_span": {"start": 0, "end": 30},
            }
        ],
    )

    def _fake_upsert(conn, *, trial_id, parser_version, criteria_json, coverage_stats):
        captured["trial_id"] = trial_id
        captured["parser_version"] = parser_version
        captured["criteria_json"] = criteria_json
        captured["coverage_stats"] = coverage_stats

    def _fake_write_log(
        conn, *, run_id, nct_id, parser_version, status, error_message
    ) -> None:
        logs.append(
            {
                "run_id": run_id,
                "nct_id": nct_id,
                "parser_version": parser_version,
                "status": status,
                "error_message": error_message,
            }
        )

    monkeypatch.setattr(tasks, "_upsert_trial_criteria", _fake_upsert)
    monkeypatch.setattr(tasks, "_write_parse_log", _fake_write_log)

    stats = parse_trial("NCT123", parser_version="rule_v1")

    assert stats.nct_id == "NCT123"
    assert stats.parser_version == "rule_v1"
    assert stats.status == "SUCCESS"
    assert stats.rule_count == 1
    assert stats.unknown_count == 0
    assert captured["trial_id"] == "trial-uuid"
    assert captured["coverage_stats"]["total_rules"] == 1
    assert captured["coverage_stats"]["failed_rules"] == 0
    assert captured["coverage_stats"]["coverage_ratio"] == 1.0
    assert logs[-1]["status"] == "SUCCESS"
    assert logs[-1]["error_message"] is None
    assert fake_conn.rollbacks == 0


def test_parse_trial_records_failed_log(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")

    fake_conn = _FakeConn()
    logs = []

    monkeypatch.setattr(tasks.psycopg, "connect", lambda _: fake_conn)
    monkeypatch.setattr(tasks, "_ensure_tables", lambda conn: None)
    monkeypatch.setattr(
        tasks,
        "_fetch_trial_for_parse",
        lambda conn, nct_id: {
            "id": "trial-uuid",
            "nct_id": nct_id,
            "eligibility_text": "Inclusion: Adults aged 18 years or older.",
        },
    )
    monkeypatch.setattr(
        tasks,
        "parse_criteria_v1",
        lambda text: (_ for _ in ()).throw(ValueError("parser crashed")),
    )
    monkeypatch.setattr(tasks, "_upsert_trial_criteria", lambda *args, **kwargs: None)

    def _fake_write_log(
        conn, *, run_id, nct_id, parser_version, status, error_message
    ) -> None:
        logs.append(
            {
                "status": status,
                "error_message": error_message,
                "nct_id": nct_id,
                "parser_version": parser_version,
            }
        )

    monkeypatch.setattr(tasks, "_write_parse_log", _fake_write_log)

    with pytest.raises(ValueError, match="parser crashed"):
        parse_trial("NCT999", parser_version="rule_v1")

    assert logs[-1]["status"] == "FAILED"
    assert "parser crashed" in str(logs[-1]["error_message"])
    assert logs[-1]["nct_id"] == "NCT999"
    assert logs[-1]["parser_version"] == "rule_v1"
    assert fake_conn.rollbacks == 1


def test_compute_coverage_stats_counts_unknown_as_failed() -> None:
    coverage_stats = _compute_coverage_stats(
        [
            {"field": "age", "certainty": "high"},
            {"field": "other", "certainty": "low"},
            {"field": "condition", "certainty": "low"},
        ]
    )

    assert coverage_stats["total_rules"] == 3
    assert coverage_stats["known_rules"] == 1
    assert coverage_stats["unknown_rules"] == 2
    assert coverage_stats["failed_rules"] == 2
    assert coverage_stats["coverage_ratio"] == pytest.approx(0.3333, abs=0.0001)


def test_sync_trials_auto_parses_new_trials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")
    fake_conn = _FakeConn()

    class _FakeClient:
        def search_studies(self, condition, status=None, page_token=None, page_size=100):
            return {"studies": [{"stub": True}], "nextPageToken": None}

    parse_calls = []

    monkeypatch.setattr(tasks.psycopg, "connect", lambda _: fake_conn)
    monkeypatch.setattr(tasks, "CTGovClient", lambda: _FakeClient())
    monkeypatch.setattr(tasks, "_ensure_tables", lambda conn: None)
    monkeypatch.setattr(tasks, "_write_sync_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        tasks,
        "_extract_trial",
        lambda study: {"nct_id": "NCT123", "data_timestamp": None},
    )
    monkeypatch.setattr(tasks, "_upsert_trial", lambda conn, trial: True)
    monkeypatch.setattr(
        tasks,
        "parse_trial",
        lambda nct_id, parser_version="rule_v1": parse_calls.append(
            (nct_id, parser_version)
        ),
    )

    stats = sync_trials(condition="diabetes", status="RECRUITING", page_limit=1)

    assert stats.processed == 1
    assert stats.inserted == 1
    assert stats.updated == 0
    assert parse_calls == [("NCT123", "rule_v1")]


def test_sync_trials_does_not_auto_parse_updated_trials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")
    fake_conn = _FakeConn()

    class _FakeClient:
        def search_studies(self, condition, status=None, page_token=None, page_size=100):
            return {"studies": [{"stub": True}], "nextPageToken": None}

    parse_calls = []

    monkeypatch.setattr(tasks.psycopg, "connect", lambda _: fake_conn)
    monkeypatch.setattr(tasks, "CTGovClient", lambda: _FakeClient())
    monkeypatch.setattr(tasks, "_ensure_tables", lambda conn: None)
    monkeypatch.setattr(tasks, "_write_sync_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        tasks,
        "_extract_trial",
        lambda study: {"nct_id": "NCT456", "data_timestamp": None},
    )
    monkeypatch.setattr(tasks, "_upsert_trial", lambda conn, trial: False)
    monkeypatch.setattr(
        tasks,
        "parse_trial",
        lambda nct_id, parser_version="rule_v1": parse_calls.append(
            (nct_id, parser_version)
        ),
    )

    stats = sync_trials(condition="diabetes", status="RECRUITING", page_limit=1)

    assert stats.processed == 1
    assert stats.inserted == 0
    assert stats.updated == 1
    assert parse_calls == []
