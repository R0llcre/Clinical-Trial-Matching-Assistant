from __future__ import annotations

from generate_parsing_relabel_tasks import build_relabel_tasks


def _rule(
    *,
    rule_type: str,
    field: str,
    operator: str,
    value,
    evidence: str = "evidence",
):
    return {
        "type": rule_type,
        "field": field,
        "operator": operator,
        "value": value,
        "unit": None,
        "evidence_text": evidence,
    }


def test_build_relabel_tasks_prioritizes_critical_field_misses() -> None:
    rows = [
        {
            "nct_id": "NCT_A",
            "eligibility_text": "text a",
            "labeled_rules": [
                _rule(
                    rule_type="EXCLUSION",
                    field="history",
                    operator="NO_HISTORY",
                    value="brain metastases",
                ),
            ],
        },
        {
            "nct_id": "NCT_B",
            "eligibility_text": "text b",
            "labeled_rules": [
                _rule(
                    rule_type="INCLUSION",
                    field="condition",
                    operator="IN",
                    value="diabetes",
                ),
            ],
        },
    ]
    predicted_by_nct = {"NCT_A": [], "NCT_B": []}

    tasks, manifest = build_relabel_tasks(
        rows=rows,
        predicted_by_nct=predicted_by_nct,
        target_trials=2,
        task_id_prefix="parsing-relabel-r1",
        guideline_version="m5-v1",
        critical_fields={"history", "medication", "procedure", "lab", "other"},
        max_diff_rules=10,
    )

    assert manifest["selected_trials"] == 2
    assert tasks[0]["nct_id"] == "NCT_A"
    assert tasks[0]["priority_score"] > tasks[1]["priority_score"]


def test_build_relabel_tasks_prioritizes_contract_errors() -> None:
    rows = [
        {
            "nct_id": "NCT_ERR",
            "eligibility_text": "text err",
            "labeled_rules": [
                _rule(
                    rule_type="INCLUSION",
                    field="sex",
                    operator="IN",
                    value="male",
                ),
            ],
        },
        {
            "nct_id": "NCT_OK",
            "eligibility_text": "text ok",
            "labeled_rules": [],
        },
    ]
    predicted_by_nct = {"NCT_ERR": [], "NCT_OK": []}

    tasks, _ = build_relabel_tasks(
        rows=rows,
        predicted_by_nct=predicted_by_nct,
        target_trials=2,
        task_id_prefix="parsing-relabel-r1",
        guideline_version="m5-v1",
        critical_fields={"history", "medication", "procedure", "lab", "other"},
        max_diff_rules=10,
    )

    assert tasks[0]["nct_id"] == "NCT_ERR"
    assert tasks[0]["priority_breakdown"]["contract_error_count"] == 1
