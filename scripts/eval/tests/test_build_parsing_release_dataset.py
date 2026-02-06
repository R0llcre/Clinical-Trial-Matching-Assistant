from __future__ import annotations

from build_parsing_release_dataset import build_dataset, validate_rule


def test_validate_rule_rejects_age_rule_without_age_semantics() -> None:
    rule = {
        "type": "INCLUSION",
        "field": "age",
        "operator": ">=",
        "value": 2,
        "unit": "years",
        "evidence_text": "No serum creatinine greater than 2.0 mg/dL on at least 2 occasions.",
    }
    ok, reason = validate_rule(rule, eligibility_text=rule["evidence_text"])
    assert ok is False
    assert reason == "age_semantics_mismatch"


def test_build_dataset_filters_invalid_rules_and_keeps_valid_age_rule() -> None:
    rows = [
        {
            "nct_id": "N1",
            "eligibility_text": "Age equal to or older than 18. No serum creatinine greater than 2.0 mg/dL.",
            "labeled_rules": [
                {
                    "type": "INCLUSION",
                    "field": "age",
                    "operator": ">=",
                    "value": 18,
                    "unit": "years",
                    "evidence_text": "Age equal to or older than 18",
                },
                {
                    "type": "INCLUSION",
                    "field": "age",
                    "operator": ">=",
                    "value": 2,
                    "unit": "years",
                    "evidence_text": "No serum creatinine greater than 2.0 mg/dL",
                },
            ],
        }
    ]

    output, manifest = build_dataset(rows)
    assert len(output) == 1
    assert len(output[0]["labeled_rules"]) == 1
    assert output[0]["labeled_rules"][0]["value"] == 18
    assert manifest["kept_rule_count"] == 1
    assert manifest["dropped_rule_count"] == 1
    assert manifest["dropped_by_reason"]["age_semantics_mismatch"] == 1
