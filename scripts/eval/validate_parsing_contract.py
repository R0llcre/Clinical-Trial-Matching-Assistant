#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

_ALLOWED_TYPES = {"INCLUSION", "EXCLUSION"}
_ALLOWED_FIELDS = {
    "age",
    "sex",
    "condition",
    "medication",
    "lab",
    "procedure",
    "history",
    "other",
}
_ALLOWED_FIELD_OPERATORS = {
    "age": {">=", "<="},
    "sex": {"="},
    "condition": {"IN", "NOT_IN"},
    "medication": {"IN", "NOT_IN", "WITHIN_LAST"},
    "lab": {">=", "<=", "IN"},
    "procedure": {"IN", "NOT_IN", "WITHIN_LAST"},
    "history": {"IN", "NO_HISTORY", "WITHIN_LAST"},
    "other": {"IN", "EXISTS"},
}
_TIME_UNITS = {"days", "weeks", "months", "years"}
_SEX_VALUES = {"male", "female", "all"}
_DEPRECATED_VALUES = {
    "manual review needed",
    "eligibility criterion",
    "study specific condition",
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
                raise ValueError(f"{path}:{line_no} row must be json object")
            rows.append(payload)
    return rows


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _as_lower_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _append_issue(
    issues: List[Dict[str, Any]],
    *,
    severity: str,
    code: str,
    location: str,
    message: str,
) -> None:
    issues.append(
        {
            "severity": severity,
            "code": code,
            "location": location,
            "message": message,
        }
    )


def _validate_rule(
    *,
    rule: Dict[str, Any],
    location: str,
    issues: List[Dict[str, Any]],
) -> None:
    rule_type = str(rule.get("type") or "").upper()
    field = str(rule.get("field") or "").strip().lower()
    operator = str(rule.get("operator") or "").upper()
    value = rule.get("value")
    unit = rule.get("unit")
    evidence_text = rule.get("evidence_text")

    if rule_type not in _ALLOWED_TYPES:
        _append_issue(
            issues,
            severity="error",
            code="TYPE_INVALID",
            location=location,
            message=f"type must be one of {_ALLOWED_TYPES}",
        )
    if field not in _ALLOWED_FIELDS:
        _append_issue(
            issues,
            severity="error",
            code="FIELD_INVALID",
            location=location,
            message=f"field must be one of {_ALLOWED_FIELDS}",
        )
        return

    allowed_operators = _ALLOWED_FIELD_OPERATORS[field]
    if operator not in allowed_operators:
        _append_issue(
            issues,
            severity="error",
            code="FIELD_OPERATOR_INVALID",
            location=location,
            message=f"operator {operator} not allowed for field {field}",
        )

    if not isinstance(evidence_text, str) or not evidence_text.strip():
        _append_issue(
            issues,
            severity="error",
            code="EVIDENCE_EMPTY",
            location=location,
            message="evidence_text must be non-empty string",
        )

    _validate_value_and_unit(
        field=field,
        operator=operator,
        value=value,
        unit=unit,
        location=location,
        issues=issues,
    )

    value_norm = _as_lower_text(value)
    if value_norm in _DEPRECATED_VALUES:
        _append_issue(
            issues,
            severity="warning",
            code="DEPRECATED_VALUE",
            location=location,
            message=f"value `{value}` should be migrated out of contract data",
        )


def _validate_value_and_unit(
    *,
    field: str,
    operator: str,
    value: Any,
    unit: Any,
    location: str,
    issues: List[Dict[str, Any]],
) -> None:
    if field == "age":
        if not _is_number(value):
            _append_issue(
                issues,
                severity="error",
                code="AGE_VALUE_INVALID",
                location=location,
                message="age value must be numeric",
            )
        if unit not in (None, "years"):
            _append_issue(
                issues,
                severity="error",
                code="AGE_UNIT_INVALID",
                location=location,
                message="age unit must be `years` or null",
            )
        return

    if field == "sex":
        value_norm = _as_lower_text(value)
        if value_norm not in _SEX_VALUES:
            _append_issue(
                issues,
                severity="error",
                code="SEX_VALUE_INVALID",
                location=location,
                message="sex value must be male/female/all",
            )
        if unit is not None:
            _append_issue(
                issues,
                severity="warning",
                code="SEX_UNIT_NON_NULL",
                location=location,
                message="sex unit should be null",
            )
        return

    if operator == "WITHIN_LAST":
        if not isinstance(value, int) or value <= 0:
            _append_issue(
                issues,
                severity="error",
                code="WITHIN_LAST_VALUE_INVALID",
                location=location,
                message="WITHIN_LAST value must be positive integer",
            )
        unit_norm = _as_lower_text(unit)
        if unit_norm not in _TIME_UNITS:
            _append_issue(
                issues,
                severity="error",
                code="WITHIN_LAST_UNIT_INVALID",
                location=location,
                message=f"WITHIN_LAST unit must be one of {_TIME_UNITS}",
            )
        return

    if field == "lab":
        if operator in {">=", "<="} and not _is_number(value):
            _append_issue(
                issues,
                severity="error",
                code="LAB_THRESHOLD_VALUE_INVALID",
                location=location,
                message="lab threshold value must be numeric",
            )
        if operator == "IN":
            if value is None:
                _append_issue(
                    issues,
                    severity="error",
                    code="LAB_IN_VALUE_EMPTY",
                    location=location,
                    message="lab IN value must be non-empty",
                )
            elif isinstance(value, str) and not value.strip():
                _append_issue(
                    issues,
                    severity="error",
                    code="LAB_IN_VALUE_EMPTY",
                    location=location,
                    message="lab IN value must be non-empty",
                )
        return

    if field == "other" and operator == "EXISTS":
        if value is not None:
            _append_issue(
                issues,
                severity="warning",
                code="OTHER_EXISTS_VALUE_NON_NULL",
                location=location,
                message="other+EXISTS prefers null value",
            )
        return

    if operator in {"IN", "NOT_IN", "NO_HISTORY"}:
        if not isinstance(value, str) or not value.strip():
            _append_issue(
                issues,
                severity="error",
                code="TEXT_VALUE_INVALID",
                location=location,
                message=f"{field}+{operator} requires non-empty string value",
            )


def validate_trials_file(path: Path) -> Dict[str, Any]:
    rows = _load_jsonl(path)
    issues: List[Dict[str, Any]] = []
    rule_count = 0

    for row_idx, row in enumerate(rows, start=1):
        location = f"{path}:row[{row_idx}]"
        nct_id = row.get("nct_id")
        eligibility_text = row.get("eligibility_text")
        labeled_rules = row.get("labeled_rules")

        if not isinstance(nct_id, str) or not nct_id.strip():
            _append_issue(
                issues,
                severity="error",
                code="NCT_ID_INVALID",
                location=location,
                message="nct_id must be non-empty string",
            )
        if not isinstance(eligibility_text, str) or not eligibility_text.strip():
            _append_issue(
                issues,
                severity="error",
                code="ELIGIBILITY_TEXT_INVALID",
                location=location,
                message="eligibility_text must be non-empty string",
            )
        if not isinstance(labeled_rules, list):
            _append_issue(
                issues,
                severity="error",
                code="LABELED_RULES_INVALID",
                location=location,
                message="labeled_rules must be list",
            )
            continue

        for rule_idx, rule in enumerate(labeled_rules, start=1):
            rule_count += 1
            rule_location = f"{location}.labeled_rules[{rule_idx}]"
            if not isinstance(rule, dict):
                _append_issue(
                    issues,
                    severity="error",
                    code="RULE_ROW_INVALID",
                    location=rule_location,
                    message="rule row must be object",
                )
                continue
            _validate_rule(rule=rule, location=rule_location, issues=issues)

    error_counts = Counter(
        issue["code"] for issue in issues if issue["severity"] == "error"
    )
    warning_counts = Counter(
        issue["code"] for issue in issues if issue["severity"] == "warning"
    )
    return {
        "file": str(path),
        "trial_count": len(rows),
        "rule_count": rule_count,
        "error_count": sum(error_counts.values()),
        "warning_count": sum(warning_counts.values()),
        "error_counts": dict(sorted(error_counts.items())),
        "warning_counts": dict(sorted(warning_counts.items())),
        "issues": issues,
    }


def _trim_issues(issues: Iterable[Dict[str, Any]], *, limit: int) -> List[Dict[str, Any]]:
    if limit <= 0:
        return list(issues)
    return list(issues)[:limit]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate parsing labeled_rules against parsing contract v2.",
    )
    parser.add_argument(
        "--trials",
        action="append",
        default=[],
        help="Path to trials JSONL file. Can pass multiple times.",
    )
    parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Return non-zero when warnings exist.",
    )
    parser.add_argument(
        "--max-issues",
        type=int,
        default=200,
        help="Max issues printed in output (0 for all).",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Optional output report path.",
    )
    args = parser.parse_args()

    trials_paths = args.trials or [
        "eval/data/trials_parsing_release.jsonl",
        "eval/data/trials_parsing_blind.jsonl",
    ]
    reports = [validate_trials_file(Path(path)) for path in trials_paths]
    all_issues: List[Dict[str, Any]] = []
    for report in reports:
        all_issues.extend(report["issues"])

    summary = {
        "ok": not any(report["error_count"] > 0 for report in reports),
        "files": reports,
        "total_errors": sum(report["error_count"] for report in reports),
        "total_warnings": sum(report["warning_count"] for report in reports),
        "issues": _trim_issues(all_issues, limit=args.max_issues),
    }
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary["ok"] or (args.fail_on_warnings and summary["total_warnings"] > 0):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
