from __future__ import annotations

from generate_parsing_adjudication_tasks import build_parsing_adjudication_tasks


def _input_rows() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    a_rows = [
        {
            "nct_id": "NCT1",
            "eligibility_text": "Adults >= 18. Female only.",
            "labeled_rules": [
                {"type": "INCLUSION", "field": "age", "operator": ">=", "value": 18, "unit": "years"},
                {
                    "type": "INCLUSION",
                    "field": "sex",
                    "operator": "=",
                    "value": "female",
                    "unit": None,
                },
            ],
        },
        {
            "nct_id": "NCT2",
            "eligibility_text": "Male only.",
            "labeled_rules": [
                {"type": "INCLUSION", "field": "sex", "operator": "=", "value": "male", "unit": None}
            ],
        },
    ]
    b_rows = [
        {
            "nct_id": "NCT1",
            "eligibility_text": "Adults >= 18. Female only.",
            "labeled_rules": [
                {"type": "INCLUSION", "field": "age", "operator": ">=", "value": "18", "unit": "years"},
                {"type": "INCLUSION", "field": "condition", "operator": "IN", "value": "adult", "unit": None},
            ],
        },
        {
            "nct_id": "NCT2",
            "eligibility_text": "Male only.",
            "labeled_rules": [
                {"type": "INCLUSION", "field": "sex", "operator": "=", "value": "male", "unit": None}
            ],
        },
    ]
    return a_rows, b_rows


def test_build_parsing_adjudication_tasks_detects_disagreements() -> None:
    a_rows, b_rows = _input_rows()
    rows, manifest = build_parsing_adjudication_tasks(a_rows=a_rows, b_rows=b_rows)

    assert manifest["input_trial_count"] == 2
    assert manifest["disagreement_trial_count"] == 1
    assert len(rows) == 1
    assert rows[0]["nct_id"] == "NCT1"
    assert rows[0]["shared_rule_count"] == 1
    assert rows[0]["a_only_rule_count"] == 1
    assert rows[0]["b_only_rule_count"] == 1


def test_build_parsing_adjudication_tasks_respects_max_trials() -> None:
    a_rows, b_rows = _input_rows()
    # Force both trials into disagreement.
    b_rows[1]["labeled_rules"] = []

    rows, manifest = build_parsing_adjudication_tasks(
        a_rows=a_rows,
        b_rows=b_rows,
        max_trials=1,
    )

    assert manifest["disagreement_trial_count"] == 2
    assert manifest["selected_trial_count"] == 1
    assert len(rows) == 1
