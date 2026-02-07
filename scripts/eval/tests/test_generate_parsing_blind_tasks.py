from __future__ import annotations

from generate_parsing_blind_tasks import (
    build_blind_candidates,
    build_blind_tasks,
)


def test_build_blind_candidates_excludes_release_and_dedupes() -> None:
    pending_rows = [
        {"nct_id": "NCT1", "query_support_count": 5},
        {"nct_id": "NCT2", "query_support_count": 2},
        {"nct_id": "NCT2", "query_support_count": 3},
        {"nct_id": "NCT3", "query_support_count": "bad"},
        {"query_support_count": 1},
    ]
    candidates, manifest = build_blind_candidates(
        pending_rows,
        release_nct_ids={"NCT1"},
    )

    assert [row["nct_id"] for row in candidates] == ["NCT2", "NCT3"]
    assert candidates[0]["query_support_count"] == 3
    assert candidates[1]["query_support_count"] == 0
    assert manifest["excluded_release_overlap_rows"] == 1
    assert manifest["invalid_rows"] == 1
    assert manifest["unique_candidates"] == 2


def test_build_blind_tasks_builds_prefixed_rows() -> None:
    candidates = [
        {"nct_id": "NCTA", "query_support_count": 4},
        {"nct_id": "NCTB", "query_support_count": 1},
    ]

    rows, manifest = build_blind_tasks(
        candidates,
        target_trials=3,
        task_id_prefix="parsing-blind-r1",
        guideline_version="m4-v1",
    )

    assert len(rows) == 2
    assert rows[0]["task_id"] == "parsing-blind-r1-00001"
    assert rows[1]["task_id"] == "parsing-blind-r1-00002"
    assert rows[0]["guideline_version"] == "m4-v1"
    assert rows[0]["status"] == "PENDING"
    assert manifest["requested_trials"] == 3
    assert manifest["selected_trials"] == 2
    assert manifest["shortfall"] == 1
    assert manifest["support_summary"]["min"] == 1
    assert manifest["support_summary"]["max"] == 4
