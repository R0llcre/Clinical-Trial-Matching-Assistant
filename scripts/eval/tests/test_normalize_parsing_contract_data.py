from __future__ import annotations

from normalize_parsing_contract_data import _canonical_sex_value, normalize_rows


def test_normalize_rows_rewrites_and_drops_expected_rules() -> None:
    rows = [
        {
            "nct_id": "NCTX",
            "eligibility_text": "text",
            "labeled_rules": [
                {
                    "type": "inclusion",
                    "field": "sex",
                    "operator": "IN",
                    "value": "Men or Women",
                    "unit": None,
                    "evidence_text": "Men or Women",
                },
                {
                    "type": "EXCLUSION",
                    "field": "history",
                    "operator": "EXISTS",
                    "value": "manual review needed",
                    "unit": None,
                    "evidence_text": "history",
                },
                {
                    "type": "EXCLUSION",
                    "field": "lab",
                    "operator": "<=",
                    "value": "HbA1c 8.5",
                    "unit": None,
                    "evidence_text": "HbA1c <= 8.5%",
                },
                {
                    "type": "EXCLUSION",
                    "field": "other",
                    "operator": "EXISTS",
                    "value": "  placeholder  ",
                    "unit": None,
                    "evidence_text": "placeholder",
                },
            ],
        }
    ]

    normalized, counters = normalize_rows(rows)
    output_rules = normalized[0]["labeled_rules"]

    assert len(output_rules) == 3
    sex_rule = output_rules[0]
    assert sex_rule["operator"] == "="
    assert sex_rule["value"] == "all"

    lab_rule = next(rule for rule in output_rules if rule["field"] == "lab")
    assert lab_rule["value"] == 8.5

    other_rule = next(rule for rule in output_rules if rule["field"] == "other")
    assert other_rule["operator"] == "IN"
    assert other_rule["value"] == "placeholder"

    assert counters["drop.deprecated_value"] == 1
    assert counters["rewrite.sex_in_to_eq"] == 1
    assert counters["rewrite.lab_threshold_to_numeric"] == 1


def test_canonical_sex_value_does_not_treat_female_as_all() -> None:
    assert _canonical_sex_value("female") == "female"
    assert _canonical_sex_value("male") == "male"
    assert _canonical_sex_value("men or women") == "all"
