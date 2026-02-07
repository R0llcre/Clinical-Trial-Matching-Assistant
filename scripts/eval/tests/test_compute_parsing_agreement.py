from __future__ import annotations

import pytest

from compute_parsing_agreement import compute_agreement, index_rules_by_nct


def _rows() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    a_rows = [
        {
            "nct_id": "NCT1",
            "eligibility_text": "Adults >= 18",
            "labeled_rules": [
                {"type": "INCLUSION", "field": "age", "operator": ">=", "value": 18, "unit": "years"}
            ],
        },
        {
            "nct_id": "NCT2",
            "eligibility_text": "Female only",
            "labeled_rules": [
                {"type": "INCLUSION", "field": "sex", "operator": "=", "value": "female", "unit": None}
            ],
        },
    ]
    b_rows = [
        {
            "nct_id": "NCT1",
            "eligibility_text": "Adults >= 18",
            "labeled_rules": [
                {"type": "inclusion", "field": "age", "operator": ">=", "value": "18", "unit": "years"}
            ],
        },
        {
            "nct_id": "NCT2",
            "eligibility_text": "Female only",
            "labeled_rules": [],
        },
    ]
    return a_rows, b_rows


def test_compute_agreement_basic_metrics() -> None:
    a_rows, b_rows = _rows()
    summary, mismatches = compute_agreement(
        index_rules_by_nct(a_rows),
        index_rules_by_nct(b_rows),
    )

    assert summary["trial_count"] == 2
    assert summary["exact_trial_match_count"] == 1
    assert summary["rule_set_precision"] == 1.0
    assert summary["rule_set_recall"] == 0.5
    assert summary["mismatch_trial_count"] == 1
    assert len(mismatches) == 1
    assert mismatches[0]["nct_id"] == "NCT2"


def test_compute_agreement_requires_same_nct_keys() -> None:
    a_rows, b_rows = _rows()
    b_rows.pop()
    with pytest.raises(ValueError, match="nct_id mismatch"):
        compute_agreement(index_rules_by_nct(a_rows), index_rules_by_nct(b_rows))
