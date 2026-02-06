from __future__ import annotations

from generate_relevance_adjudication_tasks import build_adjudication_tasks


def test_build_adjudication_tasks_selects_expected_reasons() -> None:
    labels = [
        {
            "query_id": "Q1",
            "nct_id": "N1",
            "relevance_label": 2,
            "rationale": "strong match",
            "annotator_id": "annotator_b",
            "guideline_version": "m4-v1",
        },
        {
            "query_id": "Q1",
            "nct_id": "N2",
            "relevance_label": 1,
            "rationale": "partial match",
            "annotator_id": "annotator_b",
            "guideline_version": "m4-v1",
        },
        {
            "query_id": "Q2",
            "nct_id": "N3",
            "relevance_label": 1,
            "rationale": "partial match",
            "annotator_id": "annotator_b",
            "guideline_version": "m4-v1",
        },
    ]
    tasks = [
        {"task_id": "t1", "query_id": "Q1", "nct_id": "N1", "band": "likely_2", "heuristic_score": 9.1},
        {"task_id": "t2", "query_id": "Q1", "nct_id": "N2", "band": "likely_2", "heuristic_score": 8.8},
        {"task_id": "t3", "query_id": "Q2", "nct_id": "N3", "band": "hard_negative", "heuristic_score": 2.0},
    ]

    out_rows, manifest = build_adjudication_tasks(
        labels=labels,
        tasks=tasks,
        ambiguous_task_ids={"t3"},
        likely2_label1_per_query=1,
    )

    assert len(out_rows) == 3
    by_pair = {(row["query_id"], row["nct_id"]): row for row in out_rows}
    assert "label_2" in by_pair[("Q1", "N1")]["selection_reasons"]
    assert "likely2_labeled1" in by_pair[("Q1", "N2")]["selection_reasons"]
    assert "annotator_ambiguous" in by_pair[("Q2", "N3")]["selection_reasons"]
    assert manifest["selected_rows"] == 3


def test_build_adjudication_tasks_applies_likely2_quota_per_query() -> None:
    labels = []
    tasks = []
    for idx in range(3):
        labels.append(
            {
                "query_id": "Q1",
                "nct_id": f"N{idx+1}",
                "relevance_label": 1,
                "rationale": "partial match",
                "annotator_id": "annotator_b",
                "guideline_version": "m4-v1",
            }
        )
        tasks.append(
            {
                "task_id": f"t{idx+1}",
                "query_id": "Q1",
                "nct_id": f"N{idx+1}",
                "band": "likely_2",
                "heuristic_score": float(10 - idx),
            }
        )

    out_rows, manifest = build_adjudication_tasks(
        labels=labels,
        tasks=tasks,
        ambiguous_task_ids=set(),
        likely2_label1_per_query=2,
    )

    assert len(out_rows) == 2
    assert manifest["selected_by_reason"]["likely2_labeled1"] == 2
