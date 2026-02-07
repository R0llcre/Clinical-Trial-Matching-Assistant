#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

_DEPRECATED_VALUES = {
    "manual review needed",
    "manual review note",
    "eligibility criterion",
}

_TEXT_OPERATORS = {"IN", "NOT_IN", "NO_HISTORY"}


def _norm_space(text: str) -> str:
    return " ".join((text or "").strip().split())


def _norm_lower(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_no} row must be object")
            rows.append(payload)
    return rows


def _dump_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def _parse_numeric(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) if isinstance(value, float) and value.is_integer() else value
    if not isinstance(value, str):
        return value
    matches = list(re.finditer(r"-?\d+(?:\.\d+)?", value))
    if not matches:
        return value
    parsed = float(matches[-1].group(0))
    return int(parsed) if parsed.is_integer() else parsed


def _canonical_sex_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = _norm_lower(value)
    tokens = set(re.findall(r"[a-z]+", text))
    has_male = "male" in tokens or "men" in tokens
    has_female = "female" in tokens or "women" in tokens
    if has_male and has_female:
        return "all"
    if has_male:
        return "male"
    if has_female:
        return "female"
    return text


def _rule_signature(rule: Dict[str, Any]) -> Tuple[str, str, str, str, str, str]:
    return (
        str(rule.get("type") or "").upper(),
        str(rule.get("field") or "").strip().lower(),
        str(rule.get("operator") or "").upper(),
        json.dumps(rule.get("value"), ensure_ascii=False, sort_keys=True),
        str(rule.get("unit") or ""),
        _norm_lower(str(rule.get("evidence_text") or "")),
    )


def normalize_rule(rule: Dict[str, Any], counters: Counter[str]) -> Dict[str, Any] | None:
    updated = dict(rule)
    updated["type"] = str(updated.get("type") or "").upper()
    updated["field"] = str(updated.get("field") or "").strip().lower()
    updated["operator"] = str(updated.get("operator") or "").upper()

    value = updated.get("value")
    value_norm = _norm_lower(str(value or ""))
    if value_norm in _DEPRECATED_VALUES:
        counters["drop.deprecated_value"] += 1
        return None

    field = updated["field"]
    operator = updated["operator"]

    if field == "sex" and operator == "IN":
        updated["operator"] = "="
        counters["rewrite.sex_in_to_eq"] += 1
        operator = "="
    if field == "history" and operator == "EXISTS":
        updated["operator"] = "IN"
        counters["rewrite.history_exists_to_in"] += 1
        operator = "IN"
    if field == "other" and operator == "EXISTS" and value is not None:
        updated["operator"] = "IN"
        counters["rewrite.other_exists_to_in"] += 1
        operator = "IN"

    if field == "sex":
        normalized_value = _canonical_sex_value(updated.get("value"))
        if normalized_value != updated.get("value"):
            counters["rewrite.sex_value_normalized"] += 1
            updated["value"] = normalized_value

    if field == "lab" and operator in {">=", "<="}:
        parsed = _parse_numeric(updated.get("value"))
        if parsed != updated.get("value"):
            counters["rewrite.lab_threshold_to_numeric"] += 1
            updated["value"] = parsed

    if operator in _TEXT_OPERATORS:
        text_value = str(updated.get("value") or "").strip()
        if not text_value:
            counters["drop.empty_text_value"] += 1
            return None
        normalized_text = _norm_space(text_value)
        if normalized_text != str(updated.get("value") or ""):
            counters["rewrite.text_value_trimmed"] += 1
        updated["value"] = normalized_text

    return updated


def normalize_rows(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Counter[str]]:
    counters: Counter[str] = Counter()
    normalized_rows: List[Dict[str, Any]] = []
    for row in rows:
        updated = dict(row)
        raw_rules = row.get("labeled_rules")
        if not isinstance(raw_rules, list):
            normalized_rows.append(updated)
            continue

        output_rules: List[Dict[str, Any]] = []
        seen = set()
        for raw_rule in raw_rules:
            if not isinstance(raw_rule, dict):
                counters["drop.non_object_rule"] += 1
                continue
            normalized = normalize_rule(raw_rule, counters)
            if normalized is None:
                continue
            signature = _rule_signature(normalized)
            if signature in seen:
                counters["drop.duplicate_rule"] += 1
                continue
            seen.add(signature)
            output_rules.append(normalized)
        updated["labeled_rules"] = output_rules
        normalized_rows.append(updated)
    return normalized_rows, counters


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize parsing annotation files to contract-friendly format.",
    )
    parser.add_argument("--input", required=True, help="Input trials JSONL")
    parser.add_argument("--output", required=True, help="Output trials JSONL")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    rows = _load_jsonl(input_path)
    normalized_rows, counters = normalize_rows(rows)
    _dump_jsonl(output_path, normalized_rows)

    summary = {
        "input": str(input_path),
        "output": str(output_path),
        "trial_count": len(rows),
        "changes": dict(sorted(counters.items())),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
