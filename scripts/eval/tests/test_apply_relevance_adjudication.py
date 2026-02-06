from __future__ import annotations

import pytest

from apply_relevance_adjudication import apply_adjudication


def test_apply_adjudication_overrides_subset_and_reports_transitions() -> None:
    base_rows = [
        {
            "query_id": "Q1",
            "nct_id": "N1",
            "relevance_label": 2,
            "rationale": "b strong",
            "annotator_id": "annotator_b",
            "guideline_version": "m4-v1",
        },
        {
            "query_id": "Q1",
            "nct_id": "N2",
            "relevance_label": 1,
            "rationale": "b partial",
            "annotator_id": "annotator_b",
            "guideline_version": "m4-v1",
        },
    ]
    adjudication_rows = [
        {
            "query_id": "Q1",
            "nct_id": "N1",
            "relevance_label": 1,
            "rationale": "a downgrade",
            "annotator_id": "annotator_a",
            "guideline_version": "m4-v1",
        }
    ]

    final_rows, manifest = apply_adjudication(
        base_rows=base_rows,
        adjudication_rows=adjudication_rows,
        output_annotator_id="adjudicated",
    )

    by_pair = {(row["query_id"], row["nct_id"]): row for row in final_rows}
    assert by_pair[("Q1", "N1")]["relevance_label"] == 1
    assert by_pair[("Q1", "N1")]["rationale"] == "a downgrade"
    assert by_pair[("Q1", "N1")]["annotator_id"] == "adjudicated"
    assert by_pair[("Q1", "N1")]["adjudicated"] is True

    assert by_pair[("Q1", "N2")]["relevance_label"] == 1
    assert by_pair[("Q1", "N2")]["annotator_id"] == "annotator_b"
    assert "adjudicated" not in by_pair[("Q1", "N2")]

    assert manifest["changed_pairs"] == 1
    assert manifest["label_transitions"]["2->1"] == 1
    assert manifest["final_label_distribution"] == {"0": 0, "1": 2, "2": 0}


def test_apply_adjudication_rejects_missing_pair_in_base() -> None:
    base_rows = [
        {"query_id": "Q1", "nct_id": "N1", "relevance_label": 1},
    ]
    adjudication_rows = [
        {"query_id": "Q2", "nct_id": "N2", "relevance_label": 2},
    ]

    with pytest.raises(ValueError, match="absent in base"):
        apply_adjudication(base_rows=base_rows, adjudication_rows=adjudication_rows)
