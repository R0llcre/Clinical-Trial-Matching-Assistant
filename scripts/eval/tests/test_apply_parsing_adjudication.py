from __future__ import annotations

import pytest

from apply_parsing_adjudication import apply_parsing_adjudication


def _rule(*, field: str, operator: str, value, rule_type: str = "INCLUSION") -> dict[str, object]:
    return {
        "type": rule_type,
        "field": field,
        "operator": operator,
        "value": value,
        "unit": None,
        "evidence_text": "evidence",
    }


def test_apply_parsing_adjudication_overrides_overlap_subset() -> None:
    base_rows = [
        {
            "nct_id": "N1",
            "eligibility_text": "text1",
            "labeled_rules": [_rule(field="condition", operator="IN", value="asthma")],
        },
        {
            "nct_id": "N2",
            "eligibility_text": "text2",
            "labeled_rules": [_rule(field="sex", operator="=", value="female")],
        },
    ]
    adjudicated_rows = [
        {
            "nct_id": "N1",
            "guideline_version": "m5-v1",
            "labeled_rules": [_rule(field="history", operator="NO_HISTORY", value="hiv")],
        },
        {
            "nct_id": "N9",
            "guideline_version": "m5-v1",
            "labeled_rules": [_rule(field="age", operator=">=", value=18)],
        },
    ]

    final_rows, manifest = apply_parsing_adjudication(
        base_rows=base_rows,
        adjudicated_rows=adjudicated_rows,
        output_annotator_id="annotator_c",
    )

    by_nct = {row["nct_id"]: row for row in final_rows}
    assert by_nct["N1"]["labeled_rules"][0]["field"] == "history"
    assert by_nct["N1"]["annotator_id"] == "annotator_c"
    assert by_nct["N1"]["adjudicated"] is True
    assert by_nct["N2"]["labeled_rules"][0]["field"] == "sex"
    assert "adjudicated" not in by_nct["N2"]

    assert manifest["overlap_trials_applied"] == 1
    assert manifest["missing_in_base"] == 1
    assert manifest["changed_trials"] == 1


def test_apply_parsing_adjudication_rejects_missing_when_strict() -> None:
    base_rows = [
        {"nct_id": "N1", "eligibility_text": "text", "labeled_rules": []},
    ]
    adjudicated_rows = [
        {"nct_id": "N2", "eligibility_text": "text", "labeled_rules": []},
    ]

    with pytest.raises(ValueError, match="absent in base"):
        apply_parsing_adjudication(
            base_rows=base_rows,
            adjudicated_rows=adjudicated_rows,
            strict_missing_in_base=True,
        )


def test_apply_parsing_adjudication_is_idempotent() -> None:
    base_rows = [
        {
            "nct_id": "N1",
            "eligibility_text": "text",
            "labeled_rules": [_rule(field="condition", operator="IN", value="asthma")],
        }
    ]
    adjudicated_rows = [
        {
            "nct_id": "N1",
            "guideline_version": "m5-v1",
            "labeled_rules": [_rule(field="condition", operator="IN", value="asthma")],
        }
    ]

    first_rows, first_manifest = apply_parsing_adjudication(
        base_rows=base_rows,
        adjudicated_rows=adjudicated_rows,
        output_annotator_id="annotator_c",
    )
    second_rows, second_manifest = apply_parsing_adjudication(
        base_rows=first_rows,
        adjudicated_rows=adjudicated_rows,
        output_annotator_id="annotator_c",
    )

    assert first_rows == second_rows
    assert first_manifest["changed_trials"] == 0
    assert second_manifest["changed_trials"] == 0
