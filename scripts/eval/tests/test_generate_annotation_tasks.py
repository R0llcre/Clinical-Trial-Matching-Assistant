from __future__ import annotations

from generate_annotation_tasks import generate_parsing_tasks, generate_retrieval_tasks


def _sample_rows() -> list[dict[str, object]]:
    return [
        {"query_id": "Q1", "nct_id": "N1", "relevance_label": 2},
        {"query_id": "Q1", "nct_id": "N2", "relevance_label": 1},
        {"query_id": "Q2", "nct_id": "N1", "relevance_label": 0},
        {"query_id": "Q2", "nct_id": "N3", "relevance_label": 2},
    ]


def test_generate_retrieval_tasks_uses_unlabeled_cross_product_pairs() -> None:
    tasks, manifest = generate_retrieval_tasks(_sample_rows(), target_pairs=10)

    # Full cross product is 2 queries x 3 nct_ids = 6 pairs, 4 already labeled.
    assert manifest["cross_product_pairs"] == 6
    assert manifest["candidate_unlabeled_pairs"] == 2
    assert manifest["generated_tasks"] == 2
    assert tasks[0]["query_id"] == "Q1"
    assert tasks[0]["nct_id"] == "N3"
    assert tasks[1]["query_id"] == "Q2"
    assert tasks[1]["nct_id"] == "N2"


def test_generate_parsing_tasks_ranks_by_query_support_count() -> None:
    tasks, manifest = generate_parsing_tasks(_sample_rows(), target_trials=2)

    assert manifest["candidate_trials"] == 3
    assert manifest["generated_tasks"] == 2
    assert tasks[0]["nct_id"] == "N1"
    assert tasks[0]["query_support_count"] == 2
