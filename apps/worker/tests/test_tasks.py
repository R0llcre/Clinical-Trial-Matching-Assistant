import datetime as dt

import pytest

import tasks
from tasks import (
    ParseStats,
    _build_query_term,
    _compute_coverage_stats,
    _extract_trial,
    parse_trial,
    reparse_recent_trials,
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


def test_ctgov_client_global_condition_omits_query_term(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, dict[str, str]] = {}

    def _fake_request_json(self, path: str, params: dict[str, str]):
        captured["params"] = params
        return {"studies": [], "nextPageToken": None}

    monkeypatch.setattr(tasks.CTGovClient, "_request_json", _fake_request_json)
    client = tasks.CTGovClient(base_url="https://example.invalid")

    client.search_studies(
        condition="__all__",
        status="RECRUITING,NOT_YET_RECRUITING",
        page_token=None,
        page_size=123,
    )

    params = captured["params"]
    assert "query.term" not in params
    assert params["filter.overallStatus"] == "RECRUITING,NOT_YET_RECRUITING"
    assert params["pageSize"] == "123"


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


def test_sync_trials_progressive_backfill_uses_existing_cursor(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")
    monkeypatch.setenv("SYNC_PROGRESSIVE_BACKFILL", "1")
    monkeypatch.setenv("SYNC_REFRESH_PAGES", "1")
    monkeypatch.setenv("SYNC_TARGET_TRIAL_TOTAL", "0")

    fake_conn = _FakeConn()
    monkeypatch.setattr(tasks.psycopg, "connect", lambda _: fake_conn)
    monkeypatch.setattr(tasks, "_ensure_tables", lambda conn: None)
    monkeypatch.setattr(tasks, "_write_sync_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        tasks,
        "_extract_trial",
        lambda study: {
            "nct_id": "NCT1",
            "title": "T",
            "status": None,
            "phase": None,
            "conditions": [],
            "eligibility_text": None,
            "locations_json": [],
            "raw_json": {},
            "data_timestamp": dt.datetime.utcnow(),
        },
    )
    monkeypatch.setattr(tasks, "_upsert_trial", lambda conn, trial: False)
    monkeypatch.setattr(tasks, "_trial_total", lambda conn: 0)

    calls = []
    pages = {
        None: {"studies": [{"x": 1}], "nextPageToken": "token-p2"},
        "token-p9": {"studies": [{"x": 2}], "nextPageToken": "token-p10"},
        "token-p10": {"studies": [{"x": 3}], "nextPageToken": "token-p11"},
    }

    class _FakeClient:
        def search_studies(
            self, *, condition, status=None, page_token=None, page_size=100
        ):
            calls.append(page_token)
            return pages[page_token]

    monkeypatch.setattr(tasks, "CTGovClient", lambda: _FakeClient())
    monkeypatch.setattr(
        tasks, "_read_sync_cursor", lambda conn, *, condition, trial_status: "token-p9"
    )
    written = {}

    def _fake_write_cursor(conn, *, condition, trial_status, next_page_token) -> None:
        written["condition"] = condition
        written["trial_status"] = trial_status
        written["next_page_token"] = next_page_token

    monkeypatch.setattr(tasks, "_write_sync_cursor", _fake_write_cursor)

    sync_trials(condition="cancer", page_limit=3, page_size=100)

    assert calls == [None, "token-p9", "token-p10"]
    assert written["condition"] == "cancer"
    assert written["trial_status"] == ""
    assert written["next_page_token"] == "token-p11"


def test_sync_trials_progressive_backfill_starts_from_refresh_token_when_no_cursor(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")
    monkeypatch.setenv("SYNC_PROGRESSIVE_BACKFILL", "1")
    monkeypatch.setenv("SYNC_REFRESH_PAGES", "1")
    monkeypatch.setenv("SYNC_TARGET_TRIAL_TOTAL", "0")

    fake_conn = _FakeConn()
    monkeypatch.setattr(tasks.psycopg, "connect", lambda _: fake_conn)
    monkeypatch.setattr(tasks, "_ensure_tables", lambda conn: None)
    monkeypatch.setattr(tasks, "_write_sync_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks, "_extract_trial", lambda study: {"nct_id": "NCT1"})
    monkeypatch.setattr(tasks, "_upsert_trial", lambda conn, trial: False)
    monkeypatch.setattr(tasks, "_trial_total", lambda conn: 0)

    calls = []
    pages = {
        None: {"studies": [{"x": 1}], "nextPageToken": "token-p2"},
        "token-p2": {"studies": [{"x": 2}], "nextPageToken": "token-p3"},
        "token-p3": {"studies": [{"x": 3}], "nextPageToken": "token-p4"},
    }

    class _FakeClient:
        def search_studies(
            self, *, condition, status=None, page_token=None, page_size=100
        ):
            calls.append(page_token)
            return pages[page_token]

    monkeypatch.setattr(tasks, "CTGovClient", lambda: _FakeClient())
    monkeypatch.setattr(tasks, "_read_sync_cursor", lambda *args, **kwargs: None)
    written = {}

    def _fake_write_cursor(conn, *, condition, trial_status, next_page_token) -> None:
        written["next_page_token"] = next_page_token

    monkeypatch.setattr(tasks, "_write_sync_cursor", _fake_write_cursor)

    sync_trials(condition="cancer", page_limit=3, page_size=100)

    assert calls == [None, "token-p2", "token-p3"]
    assert written["next_page_token"] == "token-p4"


def test_sync_trials_progressive_backfill_disabled_when_target_cap_reached(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")
    monkeypatch.setenv("SYNC_PROGRESSIVE_BACKFILL", "1")
    monkeypatch.setenv("SYNC_REFRESH_PAGES", "1")
    monkeypatch.setenv("SYNC_TARGET_TRIAL_TOTAL", "50000")

    fake_conn = _FakeConn()
    monkeypatch.setattr(tasks.psycopg, "connect", lambda _: fake_conn)
    monkeypatch.setattr(tasks, "_ensure_tables", lambda conn: None)
    monkeypatch.setattr(tasks, "_write_sync_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks, "_extract_trial", lambda study: {"nct_id": "NCT1"})
    monkeypatch.setattr(tasks, "_upsert_trial", lambda conn, trial: False)
    monkeypatch.setattr(tasks, "_trial_total", lambda conn: 50000)
    monkeypatch.setattr(
        tasks,
        "_read_sync_cursor",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("_read_sync_cursor should not be called when cap reached")
        ),
    )
    monkeypatch.setattr(
        tasks,
        "_write_sync_cursor",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("_write_sync_cursor should not be called when cap reached")
        ),
    )

    calls = []
    pages = {None: {"studies": [{"x": 1}], "nextPageToken": "token-p2"}}

    class _FakeClient:
        def search_studies(
            self, *, condition, status=None, page_token=None, page_size=100
        ):
            calls.append(page_token)
            return pages[page_token]

    monkeypatch.setattr(tasks, "CTGovClient", lambda: _FakeClient())

    sync_trials(condition="cancer", page_limit=3, page_size=100)

    assert calls == [None]


def test_sync_trials_prune_called_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")
    monkeypatch.setenv("SYNC_PROGRESSIVE_BACKFILL", "1")
    monkeypatch.setenv("SYNC_REFRESH_PAGES", "1")
    monkeypatch.setenv("SYNC_TARGET_TRIAL_TOTAL", "50000")
    monkeypatch.setenv("SYNC_PRUNE_TO_STATUS_FILTER", "1")

    fake_conn = _FakeConn()
    monkeypatch.setattr(tasks.psycopg, "connect", lambda _: fake_conn)
    monkeypatch.setattr(tasks, "_ensure_tables", lambda conn: None)
    monkeypatch.setattr(tasks, "_write_sync_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks, "_extract_trial", lambda study: {"nct_id": "NCT1"})
    monkeypatch.setattr(tasks, "_upsert_trial", lambda conn, trial: False)

    order: list[str] = []

    def _fake_prune(conn, *, allowed_statuses):
        order.append("prune")
        assert allowed_statuses == [
            "RECRUITING",
            "NOT_YET_RECRUITING",
            "ENROLLING_BY_INVITATION",
        ]
        return 0, 0

    def _fake_trial_total(conn):
        order.append("trial_total")
        return 0

    monkeypatch.setattr(tasks, "_prune_trials_to_status_filter", _fake_prune)
    monkeypatch.setattr(tasks, "_trial_total", _fake_trial_total)
    monkeypatch.setattr(tasks, "_read_sync_cursor", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks, "_write_sync_cursor", lambda *args, **kwargs: None)

    pages = {None: {"studies": [{"x": 1}], "nextPageToken": None}}

    class _FakeClient:
        def search_studies(
            self, *, condition, status=None, page_token=None, page_size=100
        ):
            return pages[page_token]

    monkeypatch.setattr(tasks, "CTGovClient", lambda: _FakeClient())

    sync_trials(
        condition="cancer",
        status="RECRUITING,NOT_YET_RECRUITING,ENROLLING_BY_INVITATION",
        page_limit=1,
        page_size=100,
    )

    assert order == ["prune", "trial_total"]


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
    assert stats.parser_source == "rule_v1"
    assert stats.fallback_used is False
    assert stats.fallback_reason is None
    assert stats.llm_budget_exceeded is False
    assert captured["trial_id"] == "trial-uuid"
    assert captured["coverage_stats"]["total_rules"] == 1
    assert captured["coverage_stats"]["failed_rules"] == 0
    assert captured["coverage_stats"]["coverage_ratio"] == 1.0
    assert logs[-1]["status"] == "SUCCESS"
    assert logs[-1]["error_message"] is None
    assert fake_conn.rollbacks == 0


def test_parse_trial_llm_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")

    fake_conn = _FakeConn()
    captured = {}
    logs = []
    usage_logs = []

    monkeypatch.setattr(tasks.psycopg, "connect", lambda _: fake_conn)
    monkeypatch.setattr(tasks, "_ensure_tables", lambda conn: None)
    monkeypatch.setattr(tasks, "_is_llm_budget_exceeded", lambda conn, usage_date: False)
    monkeypatch.setattr(tasks, "_daily_llm_token_usage", lambda conn, usage_date: 30)
    monkeypatch.setattr(tasks, "_read_llm_daily_token_budget", lambda: 200)
    monkeypatch.setattr(
        tasks,
        "_fetch_trial_for_parse",
        lambda conn, nct_id: {
            "id": "trial-uuid",
            "nct_id": nct_id,
            "eligibility_text": "Female participants only",
        },
    )
    monkeypatch.setattr(
        tasks,
        "parse_criteria_llm_v1_with_fallback",
        lambda text: (
            [
                {
                    "id": "rule-1",
                    "type": "INCLUSION",
                    "field": "sex",
                    "operator": "=",
                    "value": "female",
                    "unit": None,
                    "time_window": None,
                    "certainty": "high",
                    "evidence_text": "Female participants only",
                    "source_span": {"start": 0, "end": 24},
                }
            ],
            {
                "parser_source": "llm_v1",
                "fallback_used": False,
                "fallback_reason": None,
                "llm_usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                },
            },
        ),
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
    monkeypatch.setattr(
        tasks,
        "_write_llm_usage_log",
        lambda conn, *, run_id, nct_id, parser_version, usage: usage_logs.append(
            {
                "run_id": run_id,
                "nct_id": nct_id,
                "parser_version": parser_version,
                "usage": usage,
            }
        ),
    )

    stats = parse_trial("NCT123", parser_version="llm_v1")

    assert stats.nct_id == "NCT123"
    assert stats.parser_version == "llm_v1"
    assert stats.status == "SUCCESS"
    assert stats.rule_count == 1
    assert stats.unknown_count == 0
    assert stats.parser_source == "llm_v1"
    assert stats.fallback_used is False
    assert stats.fallback_reason is None
    assert stats.llm_budget_exceeded is False
    assert captured["trial_id"] == "trial-uuid"
    assert captured["parser_version"] == "llm_v1"
    assert captured["coverage_stats"]["parser_source"] == "llm_v1"
    assert captured["coverage_stats"]["fallback_used"] is False
    assert captured["coverage_stats"]["llm_usage"]["total_tokens"] == 30
    assert captured["coverage_stats"]["llm_budget"]["daily_token_budget"] == 200
    assert captured["coverage_stats"]["llm_budget"]["daily_tokens_used"] == 30
    assert usage_logs and usage_logs[0]["usage"]["total_tokens"] == 30
    assert logs[-1]["status"] == "SUCCESS"
    assert logs[-1]["error_message"] is None
    assert fake_conn.rollbacks == 0


def test_parse_trial_llm_fallback_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")

    fake_conn = _FakeConn()
    captured = {}
    usage_logs = []

    monkeypatch.setattr(tasks.psycopg, "connect", lambda _: fake_conn)
    monkeypatch.setattr(tasks, "_ensure_tables", lambda conn: None)
    monkeypatch.setattr(tasks, "_is_llm_budget_exceeded", lambda conn, usage_date: False)
    monkeypatch.setattr(tasks, "_daily_llm_token_usage", lambda conn, usage_date: 0)
    monkeypatch.setattr(tasks, "_read_llm_daily_token_budget", lambda: 200)
    monkeypatch.setattr(
        tasks,
        "_fetch_trial_for_parse",
        lambda conn, nct_id: {
            "id": "trial-uuid",
            "nct_id": nct_id,
            "eligibility_text": "Adults only",
        },
    )
    monkeypatch.setattr(
        tasks,
        "parse_criteria_llm_v1_with_fallback",
        lambda text: (
            [
                {
                    "id": "rule-1",
                    "type": "INCLUSION",
                    "field": "age",
                    "operator": ">=",
                    "value": 18,
                    "unit": "years",
                    "time_window": None,
                    "certainty": "high",
                    "evidence_text": "Adults only",
                    "source_span": {"start": 0, "end": 11},
                }
            ],
            {
                "parser_source": "rule_v1",
                "fallback_used": True,
                "fallback_reason": "llm parser disabled",
                "llm_usage": None,
            },
        ),
    )
    monkeypatch.setattr(tasks, "_write_parse_log", lambda *args, **kwargs: None)

    def _fake_upsert(conn, *, trial_id, parser_version, criteria_json, coverage_stats):
        captured["parser_version"] = parser_version
        captured["coverage_stats"] = coverage_stats

    monkeypatch.setattr(tasks, "_upsert_trial_criteria", _fake_upsert)
    monkeypatch.setattr(
        tasks,
        "_write_llm_usage_log",
        lambda conn, *, run_id, nct_id, parser_version, usage: usage_logs.append(
            usage
        ),
    )

    stats = parse_trial("NCT234", parser_version="llm_v1")

    assert stats.status == "SUCCESS"
    assert stats.parser_version == "llm_v1"
    assert stats.rule_count == 1
    assert stats.parser_source == "rule_v1"
    assert stats.fallback_used is True
    assert "disabled" in str(stats.fallback_reason)
    assert stats.llm_budget_exceeded is False
    assert captured["parser_version"] == "llm_v1"
    assert captured["coverage_stats"]["parser_source"] == "rule_v1"
    assert captured["coverage_stats"]["fallback_used"] is True
    assert "disabled" in captured["coverage_stats"]["fallback_reason"]
    assert captured["coverage_stats"]["llm_budget"]["daily_tokens_used"] == 0
    assert usage_logs == []
    assert fake_conn.rollbacks == 0


def test_parse_trial_llm_records_usage_log_even_when_fallback_to_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")

    fake_conn = _FakeConn()
    usage_logs = []

    monkeypatch.setattr(tasks.psycopg, "connect", lambda _: fake_conn)
    monkeypatch.setattr(tasks, "_ensure_tables", lambda conn: None)
    monkeypatch.setattr(tasks, "_is_llm_budget_exceeded", lambda conn, usage_date: False)
    monkeypatch.setattr(tasks, "_daily_llm_token_usage", lambda conn, usage_date: 0)
    monkeypatch.setattr(tasks, "_read_llm_daily_token_budget", lambda: 200)
    monkeypatch.setattr(
        tasks,
        "_fetch_trial_for_parse",
        lambda conn, nct_id: {
            "id": "trial-uuid",
            "nct_id": nct_id,
            "eligibility_text": "Adults only",
        },
    )
    monkeypatch.setattr(
        tasks,
        "parse_criteria_llm_v1_with_fallback",
        lambda text: (
            [
                {
                    "id": "rule-1",
                    "type": "INCLUSION",
                    "field": "age",
                    "operator": ">=",
                    "value": 18,
                    "unit": "years",
                    "time_window": None,
                    "certainty": "high",
                    "evidence_text": "Adults only",
                    "source_span": {"start": 0, "end": 11},
                }
            ],
            {
                "parser_source": "rule_v1",
                "fallback_used": True,
                "fallback_reason": "quality gate forced fallback",
                "llm_usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                },
            },
        ),
    )
    monkeypatch.setattr(tasks, "_write_parse_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks, "_upsert_trial_criteria", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        tasks,
        "_write_llm_usage_log",
        lambda conn, *, run_id, nct_id, parser_version, usage: usage_logs.append(
            {
                "run_id": run_id,
                "nct_id": nct_id,
                "parser_version": parser_version,
                "usage": usage,
            }
        ),
    )

    stats = parse_trial("NCT234", parser_version="llm_v1")

    assert stats.status == "SUCCESS"
    assert stats.parser_version == "llm_v1"
    assert stats.parser_source == "rule_v1"
    assert stats.fallback_used is True
    assert "quality gate" in str(stats.fallback_reason)
    assert usage_logs and usage_logs[0]["usage"]["total_tokens"] == 30


def test_parse_trial_llm_budget_exceeded_skips_llm_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")

    fake_conn = _FakeConn()
    captured = {}

    monkeypatch.setattr(tasks.psycopg, "connect", lambda _: fake_conn)
    monkeypatch.setattr(tasks, "_ensure_tables", lambda conn: None)
    monkeypatch.setattr(tasks, "_is_llm_budget_exceeded", lambda conn, usage_date: True)
    monkeypatch.setattr(tasks, "_daily_llm_token_usage", lambda conn, usage_date: 200)
    monkeypatch.setattr(tasks, "_read_llm_daily_token_budget", lambda: 200)
    monkeypatch.setattr(
        tasks,
        "_fetch_trial_for_parse",
        lambda conn, nct_id: {
            "id": "trial-uuid",
            "nct_id": nct_id,
            "eligibility_text": "Adults only",
        },
    )
    monkeypatch.setattr(
        tasks,
        "parse_criteria_llm_v1_with_fallback",
        lambda text: (_ for _ in ()).throw(
            AssertionError("llm parser should not be called when budget exceeded")
        ),
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
                "evidence_text": "Adults only",
                "source_span": {"start": 0, "end": 11},
            }
        ],
    )
    monkeypatch.setattr(tasks, "_write_parse_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        tasks, "_write_llm_usage_log", lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("llm usage should not be logged when budget exceeded")
        )
    )

    def _fake_upsert(conn, *, trial_id, parser_version, criteria_json, coverage_stats):
        captured["parser_version"] = parser_version
        captured["coverage_stats"] = coverage_stats

    monkeypatch.setattr(tasks, "_upsert_trial_criteria", _fake_upsert)

    stats = parse_trial("NCT777", parser_version="llm_v1")

    assert stats.status == "SUCCESS"
    assert stats.parser_source == "rule_v1"
    assert stats.fallback_used is True
    assert "budget exceeded" in str(stats.fallback_reason)
    assert stats.llm_budget_exceeded is True
    assert captured["parser_version"] == "llm_v1"
    assert captured["coverage_stats"]["parser_source"] == "rule_v1"
    assert captured["coverage_stats"]["fallback_used"] is True
    assert "budget exceeded" in captured["coverage_stats"]["fallback_reason"]
    assert captured["coverage_stats"]["llm_budget"]["budget_exceeded"] is True


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


def test_parse_trial_rejects_unknown_parser_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
            "eligibility_text": "Adults only",
        },
    )
    monkeypatch.setattr(tasks, "_upsert_trial_criteria", lambda *args, **kwargs: None)

    def _fake_write_log(
        conn, *, run_id, nct_id, parser_version, status, error_message
    ) -> None:
        logs.append(
            {
                "status": status,
                "error_message": error_message,
                "parser_version": parser_version,
            }
        )

    monkeypatch.setattr(tasks, "_write_parse_log", _fake_write_log)

    with pytest.raises(ValueError, match="unsupported parser_version: bad_version"):
        parse_trial("NCT100", parser_version="bad_version")

    assert logs[-1]["status"] == "FAILED"
    assert logs[-1]["parser_version"] == "bad_version"
    assert "unsupported parser_version" in str(logs[-1]["error_message"])
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
        lambda nct_id, parser_version="rule_v1": (
            parse_calls.append((nct_id, parser_version))
            or ParseStats(
                run_id="run-1",
                nct_id=nct_id,
                parser_version=parser_version,
                status="SUCCESS",
                rule_count=1,
                unknown_count=0,
                parser_source=parser_version,
                fallback_used=False,
                fallback_reason=None,
                llm_budget_exceeded=False,
            )
        ),
    )

    stats = sync_trials(condition="diabetes", status="RECRUITING", page_limit=1)

    assert stats.processed == 1
    assert stats.inserted == 1
    assert stats.updated == 0
    assert stats.parse_success == 1
    assert stats.parse_failed == 0
    assert stats.parse_success_rate == 1.0
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
    assert stats.parse_success == 0
    assert stats.parse_failed == 0
    assert stats.parse_success_rate == 0.0
    assert parse_calls == []


def test_sync_trials_tracks_auto_parse_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")
    fake_conn = _FakeConn()

    class _FakeClient:
        def search_studies(self, condition, status=None, page_token=None, page_size=100):
            return {"studies": [{"stub": True}], "nextPageToken": None}

    monkeypatch.setattr(tasks.psycopg, "connect", lambda _: fake_conn)
    monkeypatch.setattr(tasks, "CTGovClient", lambda: _FakeClient())
    monkeypatch.setattr(tasks, "_ensure_tables", lambda conn: None)
    monkeypatch.setattr(tasks, "_write_sync_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        tasks,
        "_extract_trial",
        lambda study: {"nct_id": "NCT999", "data_timestamp": None},
    )
    monkeypatch.setattr(tasks, "_upsert_trial", lambda conn, trial: True)

    def _boom_parse_trial(nct_id, parser_version="rule_v1"):
        raise RuntimeError("parse failed")

    monkeypatch.setattr(tasks, "parse_trial", _boom_parse_trial)

    stats = sync_trials(condition="diabetes", status="RECRUITING", page_limit=1)

    assert stats.processed == 1
    assert stats.inserted == 1
    assert stats.updated == 0
    assert stats.parse_success == 0
    assert stats.parse_failed == 1
    assert stats.parse_success_rate == 0.0


def test_sync_trials_uses_llm_parser_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")
    monkeypatch.setenv("LLM_PARSER_ENABLED", "1")
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
        lambda study: {"nct_id": "NCTLLM", "data_timestamp": None},
    )
    monkeypatch.setattr(tasks, "_upsert_trial", lambda conn, trial: True)
    monkeypatch.setattr(
        tasks,
        "parse_trial",
        lambda nct_id, parser_version="rule_v1": (
            parse_calls.append((nct_id, parser_version))
            or ParseStats(
                run_id="run-llm",
                nct_id=nct_id,
                parser_version=parser_version,
                status="SUCCESS",
                rule_count=1,
                unknown_count=0,
                parser_source="llm_v1",
                fallback_used=False,
                fallback_reason=None,
                llm_budget_exceeded=False,
            )
        ),
    )

    stats = sync_trials(condition="diabetes", status="RECRUITING", page_limit=1)

    assert parse_calls == [("NCTLLM", "llm_v1")]
    assert stats.parser_version == "llm_v1"
    assert stats.parser_source_breakdown == {"llm_v1": 1}
    assert stats.fallback_reason_breakdown == {}
    assert stats.llm_budget_exceeded_count == 0


def test_sync_trials_selective_llm_triggers_for_low_coverage_rule_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")
    monkeypatch.setenv("SYNC_PARSER_VERSION", "rule_v1")
    monkeypatch.setenv("SYNC_LLM_SELECTIVE", "1")
    monkeypatch.setenv("SYNC_LLM_SELECTIVE_UNKNOWN_RATIO_THRESHOLD", "0.4")
    monkeypatch.setenv("SYNC_LLM_SELECTIVE_UNKNOWN_RULES_MIN", "2")
    monkeypatch.setenv("SYNC_LLM_SELECTIVE_MAX_LLM_CALLS_PER_RUN", "10")
    monkeypatch.setenv("LLM_PARSER_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    fake_conn = _FakeConn()

    class _FakeClient:
        def search_studies(self, condition, status=None, page_token=None, page_size=100):
            return {"studies": [{"nct_id": "NCT123"}], "nextPageToken": None}

    parse_calls = []

    def _fake_parse_trial(nct_id: str, parser_version: str = "rule_v1") -> ParseStats:
        parse_calls.append((nct_id, parser_version))
        if parser_version == "llm_v1":
            return ParseStats(
                run_id="run-llm",
                nct_id=nct_id,
                parser_version=parser_version,
                status="SUCCESS",
                rule_count=10,
                unknown_count=0,
                parser_source="llm_v1",
                fallback_used=False,
                fallback_reason=None,
                llm_budget_exceeded=False,
            )
        return ParseStats(
            run_id="run-rule",
            nct_id=nct_id,
            parser_version=parser_version,
            status="SUCCESS",
            rule_count=10,
            unknown_count=6,
            parser_source="rule_v1",
            fallback_used=False,
            fallback_reason=None,
            llm_budget_exceeded=False,
        )

    monkeypatch.setattr(tasks.psycopg, "connect", lambda _: fake_conn)
    monkeypatch.setattr(tasks, "CTGovClient", lambda: _FakeClient())
    monkeypatch.setattr(tasks, "_ensure_tables", lambda conn: None)
    monkeypatch.setattr(tasks, "_write_sync_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks, "_extract_trial", lambda study: {"nct_id": study["nct_id"]})
    monkeypatch.setattr(tasks, "_upsert_trial", lambda conn, trial: True)
    monkeypatch.setattr(tasks, "_recent_llm_usage_nct_ids", lambda *args, **kwargs: set())
    monkeypatch.setattr(tasks, "parse_trial", _fake_parse_trial)

    stats = sync_trials(condition="diabetes", status="RECRUITING", page_limit=1)

    assert parse_calls == [("NCT123", "rule_v1"), ("NCT123", "llm_v1")]
    assert stats.selective_llm_triggered == 1
    assert stats.parser_source_breakdown == {"llm_v1": 1}


def test_sync_trials_selective_llm_respects_max_per_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")
    monkeypatch.setenv("SYNC_PARSER_VERSION", "rule_v1")
    monkeypatch.setenv("SYNC_LLM_SELECTIVE", "1")
    monkeypatch.setenv("SYNC_LLM_SELECTIVE_UNKNOWN_RATIO_THRESHOLD", "0.4")
    monkeypatch.setenv("SYNC_LLM_SELECTIVE_UNKNOWN_RULES_MIN", "2")
    monkeypatch.setenv("SYNC_LLM_SELECTIVE_MAX_LLM_CALLS_PER_RUN", "2")
    monkeypatch.setenv("LLM_PARSER_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    fake_conn = _FakeConn()

    class _FakeClient:
        def search_studies(self, condition, status=None, page_token=None, page_size=100):
            return {
                "studies": [{"nct_id": "NCT1"}, {"nct_id": "NCT2"}, {"nct_id": "NCT3"}],
                "nextPageToken": None,
            }

    parse_calls = []

    def _fake_parse_trial(nct_id: str, parser_version: str = "rule_v1") -> ParseStats:
        parse_calls.append((nct_id, parser_version))
        if parser_version == "llm_v1":
            return ParseStats(
                run_id="run-llm",
                nct_id=nct_id,
                parser_version=parser_version,
                status="SUCCESS",
                rule_count=10,
                unknown_count=0,
                parser_source="llm_v1",
                fallback_used=False,
                fallback_reason=None,
                llm_budget_exceeded=False,
            )
        return ParseStats(
            run_id="run-rule",
            nct_id=nct_id,
            parser_version=parser_version,
            status="SUCCESS",
            rule_count=10,
            unknown_count=6,
            parser_source="rule_v1",
            fallback_used=False,
            fallback_reason=None,
            llm_budget_exceeded=False,
        )

    monkeypatch.setattr(tasks.psycopg, "connect", lambda _: fake_conn)
    monkeypatch.setattr(tasks, "CTGovClient", lambda: _FakeClient())
    monkeypatch.setattr(tasks, "_ensure_tables", lambda conn: None)
    monkeypatch.setattr(tasks, "_write_sync_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks, "_extract_trial", lambda study: {"nct_id": study["nct_id"]})
    monkeypatch.setattr(tasks, "_upsert_trial", lambda conn, trial: True)
    monkeypatch.setattr(tasks, "_recent_llm_usage_nct_ids", lambda *args, **kwargs: set())
    monkeypatch.setattr(tasks, "parse_trial", _fake_parse_trial)

    stats = sync_trials(condition="diabetes", status="RECRUITING", page_limit=1)

    llm_calls = [call for call in parse_calls if call[1] == "llm_v1"]
    assert len(llm_calls) == 2
    assert stats.selective_llm_triggered == 2
    assert stats.parser_source_breakdown == {"llm_v1": 2, "rule_v1": 1}
    assert stats.selective_llm_skipped_breakdown["max per run"] == 1


def test_sync_trials_backfill_parses_trials_without_criteria(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")
    monkeypatch.setenv("SYNC_PARSER_VERSION", "rule_v1")
    monkeypatch.setenv("SYNC_LLM_BACKFILL_ENABLED", "1")
    monkeypatch.setenv("SYNC_LLM_BACKFILL_LIMIT", "2")

    fake_conn = _FakeConn()

    class _FakeClient:
        def search_studies(self, condition, status=None, page_token=None, page_size=100):
            return {"studies": [], "nextPageToken": None}

    parse_calls = []

    def _fake_parse_trial(nct_id: str, parser_version: str = "rule_v1") -> ParseStats:
        parse_calls.append((nct_id, parser_version))
        return ParseStats(
            run_id="run-rule",
            nct_id=nct_id,
            parser_version=parser_version,
            status="SUCCESS",
            rule_count=5,
            unknown_count=1,
            parser_source="rule_v1",
            fallback_used=False,
            fallback_reason=None,
            llm_budget_exceeded=False,
        )

    monkeypatch.setattr(tasks.psycopg, "connect", lambda _: fake_conn)
    monkeypatch.setattr(tasks, "CTGovClient", lambda: _FakeClient())
    monkeypatch.setattr(tasks, "_ensure_tables", lambda conn: None)
    monkeypatch.setattr(tasks, "_write_sync_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks, "_select_backfill_nct_ids", lambda *args, **kwargs: ["NCTB1", "NCTB2"])
    monkeypatch.setattr(tasks, "parse_trial", _fake_parse_trial)

    stats = sync_trials(condition="diabetes", status="RECRUITING", page_limit=1)

    assert stats.backfill_selected == 2
    assert parse_calls == [("NCTB1", "rule_v1"), ("NCTB2", "rule_v1")]


def test_reparse_recent_trials_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/testdb")
    fake_conn = _FakeConn()

    monkeypatch.setattr(tasks.psycopg, "connect", lambda _: fake_conn)
    monkeypatch.setattr(tasks, "_ensure_tables", lambda conn: None)
    monkeypatch.setattr(
        tasks,
        "_select_recent_trial_nct_ids",
        lambda conn, lookback_hours, limit, condition, status: ["NCT1", "NCT2"],
    )

    def _fake_parse_trial(nct_id: str, parser_version: str = "llm_v1") -> ParseStats:
        if nct_id == "NCT2":
            raise RuntimeError("parse failed")
        return ParseStats(
            run_id="run-1",
            nct_id=nct_id,
            parser_version=parser_version,
            status="SUCCESS",
            rule_count=3,
            unknown_count=1,
            parser_source="rule_v1",
            fallback_used=True,
            fallback_reason="llm parser disabled",
            llm_budget_exceeded=False,
        )

    monkeypatch.setattr(tasks, "parse_trial", _fake_parse_trial)

    summary = reparse_recent_trials(
        parser_version="llm_v1",
        limit=20,
        lookback_hours=48,
        condition="asthma",
        status="RECRUITING",
    )

    assert summary["selected"] == 2
    assert summary["parsed_success"] == 1
    assert summary["parsed_failed"] == 1
    assert summary["parser_source_breakdown"] == {"rule_v1": 1}
    assert summary["fallback_reason_breakdown"] == {"llm parser disabled": 1}
    assert summary["llm_budget_exceeded_count"] == 0
