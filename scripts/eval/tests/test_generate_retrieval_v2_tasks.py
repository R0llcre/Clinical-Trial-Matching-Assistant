from __future__ import annotations

import json
from pathlib import Path

import pytest

from generate_retrieval_v2_tasks import (
    DEFAULT_EXCLUDE_FILES,
    build_round_batch,
    build_search_terms,
    load_excluded_pairs,
    score_trial_for_query,
)


def test_build_search_terms_includes_expected_condition_and_dedupes() -> None:
    query = {
        "query": "type 2 diabetes recruiting phase 2 in california",
        "expected_conditions": ["type 2 diabetes"],
        "expected_status": "RECRUITING",
        "expected_phase": "PHASE2",
    }

    terms = build_search_terms(query)
    normalized = {" ".join(term.lower().replace("-", " ").split()) for term in terms}

    assert "type 2 diabetes recruiting phase 2 in california" in normalized
    assert "type 2 diabetes" in normalized
    assert len(normalized) == len(terms)


def test_score_trial_for_query_prefers_likely_2_when_condition_and_phase_match() -> None:
    query = {
        "query": "metastatic breast cancer phase 3",
        "expected_conditions": ["metastatic breast cancer"],
        "expected_status": "RECRUITING",
        "expected_phase": "PHASE3",
        "expected_location": {"country": "USA", "state": None, "city": None},
    }
    trial = {
        "title": "Metastatic Breast Cancer Combination Study",
        "conditions": ["metastatic breast cancer"],
        "status": "RECRUITING",
        "phases": ["PHASE3"],
        "locations": [{"country": "USA", "state": "CA", "city": "Los Angeles"}],
    }

    score, band, features = score_trial_for_query(query, trial)
    assert band == "likely_2"
    assert score > 8.0
    assert features["condition_exact"] is True
    assert features["phase_match"] is True
    assert features["status_match"] is True


def test_score_trial_for_query_normalizes_us_location_aliases() -> None:
    query = {
        "query": "metastatic breast cancer phase 3",
        "expected_conditions": ["metastatic breast cancer"],
        "expected_status": "RECRUITING",
        "expected_phase": "PHASE3",
        "expected_location": {"country": "USA", "state": "CA", "city": None},
    }
    trial = {
        "title": "Metastatic Breast Cancer Combination Study",
        "conditions": ["metastatic breast cancer"],
        "status": "RECRUITING",
        "phases": ["PHASE3"],
        "locations": [{"country": "United States", "state": "California", "city": "Los Angeles"}],
    }

    _, band, features = score_trial_for_query(query, trial)
    assert band == "likely_2"
    assert features["location_match_score"] >= 2


def test_score_trial_for_query_tracks_intent_feature_matches() -> None:
    query = {
        "query": "migraine prevention trial for women",
        "expected_conditions": ["migraine"],
        "expected_status": None,
        "expected_phase": "PHASE2",
        "expected_location": {"country": "USA", "state": None, "city": None},
    }
    trial = {
        "title": "Phase 2 migraine prevention study in women",
        "conditions": ["migraine"],
        "status": "COMPLETED",
        "phases": ["PHASE2"],
        "locations": [{"country": "United States", "state": "Texas", "city": "Dallas"}],
    }

    _, _, features = score_trial_for_query(query, trial)
    assert features["intent_target_count"] >= 2
    assert features["intent_match_count"] >= 2


def test_build_round_batch_respects_per_query_target_and_fallback() -> None:
    pending_rows = [
        {
            "query_id": "Q1",
            "nct_id": "N1",
            "band": "likely_2",
            "heuristic_score": 10.0,
        },
        {
            "query_id": "Q1",
            "nct_id": "N2",
            "band": "likely_1",
            "heuristic_score": 9.0,
        },
        {
            "query_id": "Q1",
            "nct_id": "N3",
            "band": "hard_negative",
            "heuristic_score": 1.0,
        },
    ]

    batch, summary = build_round_batch(
        pending_rows,
        target_per_query=3,
        likely2_quota=2,
        likely1_quota=1,
        hard_negative_quota=0,
    )

    assert len(batch) == 3
    assert summary["queries"]["Q1"]["picked"] == 3
    assert summary["queries"]["Q1"]["shortfall"] == 0
    assert {row["nct_id"] for row in batch} == {"N1", "N2", "N3"}


def test_build_round_batch_supports_custom_task_id_prefix() -> None:
    pending_rows = [
        {
            "query_id": "Q1",
            "nct_id": "N1",
            "band": "likely_2",
            "heuristic_score": 10.0,
        }
    ]

    batch, _ = build_round_batch(
        pending_rows,
        target_per_query=1,
        likely2_quota=1,
        likely1_quota=0,
        hard_negative_quota=0,
        task_id_prefix="relevance-v2r2",
    )

    assert batch[0]["task_id"] == "relevance-v2r2-00001"


def test_build_round_batch_rejects_quota_sum_above_target() -> None:
    pending_rows = [
        {"query_id": "Q1", "nct_id": "N1", "band": "likely_2", "heuristic_score": 10.0},
        {"query_id": "Q1", "nct_id": "N2", "band": "likely_1", "heuristic_score": 9.0},
        {"query_id": "Q1", "nct_id": "N3", "band": "hard_negative", "heuristic_score": 8.0},
    ]

    with pytest.raises(ValueError, match="sum of quotas"):
        build_round_batch(
            pending_rows,
            target_per_query=2,
            likely2_quota=1,
            likely1_quota=1,
            hard_negative_quota=1,
        )


def test_load_excluded_pairs_reads_query_nct_keys(tmp_path: Path) -> None:
    path = tmp_path / "exclude.jsonl"
    rows = [
        {"query_id": "Q1", "nct_id": "N1"},
        {"query_id": "Q2", "nct_id": "N2", "relevance_label": 1},
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    excluded = load_excluded_pairs([path])
    assert excluded == {("Q1", "N1"), ("Q2", "N2")}


def test_default_exclude_files_use_canonical_final_sets() -> None:
    assert "eval/annotations/relevance.batch1.annotator_b.jsonl" not in DEFAULT_EXCLUDE_FILES
    assert "eval/annotations/relevance.batch2.annotator_b.jsonl" not in DEFAULT_EXCLUDE_FILES
    assert "eval/annotations/relevance.batch3.annotator_b.jsonl" not in DEFAULT_EXCLUDE_FILES
    assert "eval/annotations/relevance.batch4.annotator_b.jsonl" not in DEFAULT_EXCLUDE_FILES
    assert "eval/annotations/relevance.v2.round1_round2_round4.final.jsonl" in DEFAULT_EXCLUDE_FILES
