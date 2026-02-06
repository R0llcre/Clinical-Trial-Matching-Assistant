#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

REQUIRED_FILES = {
    "queries": "queries.jsonl",
    "trials_sample": "trials_sample.jsonl",
    "patients": "patients.jsonl",
}


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} invalid json: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_no} row must be a JSON object")
            rows.append(payload)
    return rows


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _validate_queries(rows: List[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    seen_ids = set()
    for idx, row in enumerate(rows, start=1):
        row_key = f"queries[{idx}]"
        query_id = row.get("query_id")
        query = row.get("query")
        expected_conditions = row.get("expected_conditions")
        expected_location = row.get("expected_location")

        if not isinstance(query_id, str) or not query_id.strip():
            errors.append(f"{row_key}.query_id must be non-empty string")
        elif query_id in seen_ids:
            errors.append(f"{row_key}.query_id duplicated: {query_id}")
        else:
            seen_ids.add(query_id)

        if not isinstance(query, str) or not query.strip():
            errors.append(f"{row_key}.query must be non-empty string")

        if not isinstance(expected_conditions, list) or not expected_conditions:
            errors.append(f"{row_key}.expected_conditions must be non-empty string list")
        else:
            for item in expected_conditions:
                if not isinstance(item, str) or not item.strip():
                    errors.append(
                        f"{row_key}.expected_conditions contains invalid value: {item}"
                    )

        if not isinstance(expected_location, dict):
            errors.append(f"{row_key}.expected_location must be object")
        else:
            for key in ("country", "state", "city"):
                value = expected_location.get(key)
                if value is not None and not isinstance(value, str):
                    errors.append(f"{row_key}.expected_location.{key} must be string/null")
    return errors


def _validate_rule(rule: Dict[str, Any], row_key: str) -> List[str]:
    errors: List[str] = []
    rule_type = rule.get("type")
    field = rule.get("field")
    operator = rule.get("operator")
    evidence_text = rule.get("evidence_text")
    if rule_type not in {"INCLUSION", "EXCLUSION"}:
        errors.append(f"{row_key}.type must be INCLUSION or EXCLUSION")
    if not isinstance(field, str) or not field.strip():
        errors.append(f"{row_key}.field must be non-empty string")
    if not isinstance(operator, str) or not operator.strip():
        errors.append(f"{row_key}.operator must be non-empty string")
    if not isinstance(evidence_text, str) or not evidence_text.strip():
        errors.append(f"{row_key}.evidence_text must be non-empty string")
    return errors


def _validate_trials(rows: List[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    seen_ids = set()
    for idx, row in enumerate(rows, start=1):
        row_key = f"trials_sample[{idx}]"
        nct_id = row.get("nct_id")
        eligibility_text = row.get("eligibility_text")
        labeled_rules = row.get("labeled_rules")

        if not isinstance(nct_id, str) or not nct_id.strip():
            errors.append(f"{row_key}.nct_id must be non-empty string")
        elif nct_id in seen_ids:
            errors.append(f"{row_key}.nct_id duplicated: {nct_id}")
        else:
            seen_ids.add(nct_id)

        if not isinstance(eligibility_text, str) or not eligibility_text.strip():
            errors.append(f"{row_key}.eligibility_text must be non-empty string")

        if not isinstance(labeled_rules, list):
            errors.append(f"{row_key}.labeled_rules must be list")
            continue
        for ridx, rule in enumerate(labeled_rules, start=1):
            if not isinstance(rule, dict):
                errors.append(f"{row_key}.labeled_rules[{ridx}] must be object")
                continue
            errors.extend(_validate_rule(rule, f"{row_key}.labeled_rules[{ridx}]"))
    return errors


def _validate_patients(rows: List[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    seen_ids = set()
    for idx, row in enumerate(rows, start=1):
        row_key = f"patients[{idx}]"
        patient_id = row.get("patient_id")
        demographics = row.get("demographics")
        conditions = row.get("conditions")
        labs = row.get("labs")

        if not isinstance(patient_id, str) or not patient_id.strip():
            errors.append(f"{row_key}.patient_id must be non-empty string")
        elif patient_id in seen_ids:
            errors.append(f"{row_key}.patient_id duplicated: {patient_id}")
        else:
            seen_ids.add(patient_id)

        if not isinstance(demographics, dict):
            errors.append(f"{row_key}.demographics must be object")
        else:
            age = demographics.get("age")
            sex = demographics.get("sex")
            if not _is_number(age) or age < 0:
                errors.append(f"{row_key}.demographics.age must be >=0 number")
            if not isinstance(sex, str) or not sex.strip():
                errors.append(f"{row_key}.demographics.sex must be non-empty string")

        if not isinstance(conditions, list):
            errors.append(f"{row_key}.conditions must be list")
        else:
            for condition in conditions:
                if not isinstance(condition, str) or not condition.strip():
                    errors.append(f"{row_key}.conditions contains invalid value")

        if not isinstance(labs, list):
            errors.append(f"{row_key}.labs must be list")
        else:
            for lidx, lab in enumerate(labs, start=1):
                if not isinstance(lab, dict):
                    errors.append(f"{row_key}.labs[{lidx}] must be object")
                    continue
                name = lab.get("name")
                value = lab.get("value")
                unit = lab.get("unit")
                if not isinstance(name, str) or not name.strip():
                    errors.append(f"{row_key}.labs[{lidx}].name must be non-empty string")
                if not _is_number(value):
                    errors.append(f"{row_key}.labs[{lidx}].value must be number")
                if not isinstance(unit, str) or not unit.strip():
                    errors.append(f"{row_key}.labs[{lidx}].unit must be non-empty string")
    return errors


def validate_data_dir(data_dir: Path) -> Tuple[Dict[str, int], List[str]]:
    counts: Dict[str, int] = {}
    errors: List[str] = []
    for key, filename in REQUIRED_FILES.items():
        path = data_dir / filename
        if not path.exists():
            errors.append(f"missing file: {path}")
            counts[key] = 0
            continue
        rows = _load_jsonl(path)
        counts[key] = len(rows)
        if key == "queries":
            errors.extend(_validate_queries(rows))
        elif key == "trials_sample":
            errors.extend(_validate_trials(rows))
        elif key == "patients":
            errors.extend(_validate_patients(rows))
    return counts, errors


def _iter_error_messages(errors: Iterable[str]) -> List[str]:
    return [message for message in errors]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate M4 eval data JSONL files.")
    parser.add_argument(
        "--data-dir",
        default="eval/data",
        help="Directory containing queries.jsonl/trials_sample.jsonl/patients.jsonl",
    )
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    counts, errors = validate_data_dir(data_dir)
    summary = {
        "data_dir": str(data_dir),
        "counts": counts,
        "errors": _iter_error_messages(errors),
        "ok": not errors,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
