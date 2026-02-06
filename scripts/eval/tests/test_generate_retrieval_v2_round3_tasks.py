from __future__ import annotations

from generate_retrieval_v2_round3_tasks import (
    DEFAULT_PENDING_PATH,
    apply_hard_filters,
    build_blind_rows,
    build_targeted_batch,
    determine_focus_queries,
)


def test_determine_focus_queries_auto_selects_label2_sparse_queries() -> None:
    pending_rows = [
        {"query_id": "Q1", "nct_id": "N1"},
        {"query_id": "Q2", "nct_id": "N2"},
        {"query_id": "Q3", "nct_id": "N3"},
    ]
    reference_rows = [
        {"query_id": "Q1", "nct_id": "N10", "relevance_label": 0},
        {"query_id": "Q2", "nct_id": "N20", "relevance_label": 2},
        {"query_id": "Q3", "nct_id": "N30", "relevance_label": 2},
        {"query_id": "Q3", "nct_id": "N31", "relevance_label": 2},
    ]

    focus, label2_counts = determine_focus_queries(
        pending_rows=pending_rows,
        reference_rows=reference_rows,
        max_label2_count=1,
        explicit_focus_queries=[],
    )

    assert focus == ["Q1", "Q2"]
    assert label2_counts == {"Q2": 1, "Q3": 2}


def test_build_targeted_batch_respects_quotas_and_exclusion() -> None:
    pending_rows = [
        {"query_id": "Q1", "nct_id": "N1", "band": "likely_2", "heuristic_score": 10.0},
        {"query_id": "Q1", "nct_id": "N2", "band": "likely_2", "heuristic_score": 9.0},
        {"query_id": "Q1", "nct_id": "N3", "band": "likely_1", "heuristic_score": 8.0},
        {"query_id": "Q1", "nct_id": "N4", "band": "hard_negative", "heuristic_score": 1.0},
    ]
    reference_rows = [
        {"query_id": "Q1", "nct_id": "N0", "relevance_label": 0},
    ]

    batch, manifest = build_targeted_batch(
        pending_rows=pending_rows,
        reference_rows=reference_rows,
        excluded_pairs={("Q1", "N1")},
        focus_queries=["Q1"],
        label2_counts={},
        target_per_query=3,
        likely2_quota=2,
        likely1_quota=1,
        hard_negative_quota=0,
        task_id_prefix="relevance-v2r3",
    )

    assert len(batch) == 3
    assert [row["task_id"] for row in batch] == [
        "relevance-v2r3-00001",
        "relevance-v2r3-00002",
        "relevance-v2r3-00003",
    ]
    assert {row["nct_id"] for row in batch} == {"N2", "N3", "N4"}
    assert manifest["query_summary"]["Q1"]["shortfall"] == 0


def test_build_blind_rows_removes_scoring_fields() -> None:
    batch_rows = [
        {
            "task_id": "relevance-v2r3-00001",
            "task_type": "relevance",
            "status": "PENDING",
            "guideline_version": "m4-v1",
            "query_id": "Q1",
            "nct_id": "N1",
            "title": "Trial",
            "overall_status": "RECRUITING",
            "phases": ["PHASE2"],
            "band": "likely_2",
            "heuristic_score": 9.1,
            "features": {"status_match": True},
        }
    ]

    blind_rows = build_blind_rows(batch_rows)
    row = blind_rows[0]
    assert row["task_id"] == "relevance-v2r3-00001"
    assert row["query_id"] == "Q1"
    assert "band" not in row
    assert "heuristic_score" not in row
    assert "features" not in row


def test_apply_hard_filters_drops_rows_with_constraint_mismatch() -> None:
    pending_rows = [
        {
            "query_id": "Q1",
            "nct_id": "N1",
            "features": {
                "status_match": True,
                "phase_match": True,
                "location_match_score": 1,
                "intent_target_count": 1,
                "intent_match_count": 1,
            },
        },
        {
            "query_id": "Q1",
            "nct_id": "N2",
            "features": {
                "status_match": True,
                "phase_match": False,
                "location_match_score": 1,
                "intent_target_count": 1,
                "intent_match_count": 0,
            },
        },
    ]
    query_by_id = {
        "Q1": {
            "query_id": "Q1",
            "expected_status": "RECRUITING",
            "expected_phase": "PHASE2",
            "expected_location": {"country": "USA", "state": None, "city": None},
        }
    }

    kept, manifest = apply_hard_filters(
        pending_rows=pending_rows,
        query_by_id=query_by_id,
        focus_queries=["Q1"],
        require_status_match=True,
        require_phase_match=True,
        min_location_match_score=1,
        min_intent_match_count=1,
    )

    assert len(kept) == 1
    assert kept[0]["nct_id"] == "N1"
    assert manifest["dropped_rows"] == 1
    assert manifest["drop_reasons"]["phase_mismatch"] == 1
    assert manifest["drop_reasons"]["intent_mismatch"] == 1


def test_default_pending_path_points_to_archived_round2_pool() -> None:
    assert (
        DEFAULT_PENDING_PATH
        == "eval/archive/m4_history/annotation_tasks/relevance.pending.v2.round2.jsonl"
    )
