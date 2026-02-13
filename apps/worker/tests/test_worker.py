import logging
from types import SimpleNamespace

import worker
from worker import _env_bool, _env_int, _split_csv


def test_env_int_defaults(monkeypatch) -> None:
    monkeypatch.delenv("TEST_INT", raising=False)
    assert _env_int("TEST_INT", 7) == 7


def test_env_int_invalid(monkeypatch) -> None:
    monkeypatch.setenv("TEST_INT", "oops")
    assert _env_int("TEST_INT", 9) == 9


def test_env_bool_variants(monkeypatch) -> None:
    monkeypatch.setenv("TEST_BOOL", "true")
    assert _env_bool("TEST_BOOL") is True
    monkeypatch.setenv("TEST_BOOL", "0")
    assert _env_bool("TEST_BOOL") is False


def test_split_csv() -> None:
    assert _split_csv("cancer") == ["cancer"]
    assert _split_csv("cancer, asthma , , heart failure") == [
        "cancer",
        "asthma",
        "heart failure",
    ]


def test_main_logs_parse_success_rate(monkeypatch, caplog) -> None:
    monkeypatch.setenv("SYNC_RUN_ONCE", "true")
    monkeypatch.setenv("SYNC_CONDITION", "cancer")
    stats = SimpleNamespace(
        run_id="run-1",
        processed=12,
        inserted=4,
        updated=8,
        pruned_trials=0,
        pruned_criteria=0,
        parse_success=3,
        parse_failed=1,
        parse_success_rate=0.75,
        parser_version="llm_v1",
        parser_source_breakdown={"llm_v1": 2, "rule_v1": 1},
        fallback_reason_breakdown={"llm parser disabled": 1},
        llm_budget_exceeded_count=0,
        backfill_selected=0,
        selective_llm_triggered=0,
        selective_llm_skipped_breakdown={},
    )
    monkeypatch.setattr(
        worker,
        "sync_trials",
        lambda condition, status, page_limit, page_size: stats,
    )

    with caplog.at_level(logging.INFO):
        worker.main()

    combined_logs = " | ".join(caplog.messages)
    assert "parse_success=3" in combined_logs
    assert "parse_failed=1" in combined_logs
    assert "parse_success_rate=0.75" in combined_logs
    assert "parser_source_breakdown={'llm_v1': 2, 'rule_v1': 1}" in combined_logs
