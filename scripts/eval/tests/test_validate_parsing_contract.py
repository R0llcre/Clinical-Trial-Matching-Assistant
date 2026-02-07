from __future__ import annotations

import json
from pathlib import Path

from validate_parsing_contract import validate_trials_file


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_validate_trials_file_accepts_contract_conformant_rows(tmp_path: Path) -> None:
    path = tmp_path / "trials.jsonl"
    _write_jsonl(
        path,
        [
            {
                "nct_id": "NCT00000001",
                "eligibility_text": "Adults >= 18 years. No history of stroke within 3 months.",
                "labeled_rules": [
                    {
                        "type": "INCLUSION",
                        "field": "age",
                        "operator": ">=",
                        "value": 18,
                        "unit": "years",
                        "evidence_text": "Adults >= 18 years.",
                    },
                    {
                        "type": "EXCLUSION",
                        "field": "history",
                        "operator": "WITHIN_LAST",
                        "value": 3,
                        "unit": "months",
                        "evidence_text": "No history of stroke within 3 months.",
                    },
                ],
            }
        ],
    )

    report = validate_trials_file(path)
    assert report["error_count"] == 0
    assert report["warning_count"] == 0


def test_validate_trials_file_reports_field_operator_violation(tmp_path: Path) -> None:
    path = tmp_path / "trials.jsonl"
    _write_jsonl(
        path,
        [
            {
                "nct_id": "NCT00000002",
                "eligibility_text": "Female only.",
                "labeled_rules": [
                    {
                        "type": "INCLUSION",
                        "field": "sex",
                        "operator": "IN",
                        "value": "female",
                        "unit": None,
                        "evidence_text": "Female only.",
                    }
                ],
            }
        ],
    )

    report = validate_trials_file(path)
    assert report["error_count"] == 1
    assert report["error_counts"]["FIELD_OPERATOR_INVALID"] == 1


def test_validate_trials_file_reports_deprecated_value_warning(tmp_path: Path) -> None:
    path = tmp_path / "trials.jsonl"
    _write_jsonl(
        path,
        [
            {
                "nct_id": "NCT00000003",
                "eligibility_text": "Inclusion criteria.",
                "labeled_rules": [
                    {
                        "type": "INCLUSION",
                        "field": "condition",
                        "operator": "IN",
                        "value": "study specific condition",
                        "unit": None,
                        "evidence_text": "Inclusion criteria.",
                    }
                ],
            }
        ],
    )

    report = validate_trials_file(path)
    assert report["error_count"] == 0
    assert report["warning_count"] == 1
    assert report["warning_counts"]["DEPRECATED_VALUE"] == 1
