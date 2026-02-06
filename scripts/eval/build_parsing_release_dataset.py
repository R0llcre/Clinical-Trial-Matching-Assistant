#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

ALLOWED_FIELDS = {"age", "sex", "condition", "medication", "history", "lab", "procedure", "other"}
ALLOWED_TYPES = {"INCLUSION", "EXCLUSION"}
AGE_WORDS = (
    " age ",
    "years old",
    "year old",
    "older than",
    "younger than",
    "adult",
    "pediatric",
    "paediatric",
    "adolescent",
    "child",
)
SEX_WORDS = ("male", "female", "men", "women", "boy", "girl", "sex")
LAB_WORDS = (
    "mg/dl",
    "mmol",
    "wbc",
    "platelet",
    "hemoglobin",
    "haemoglobin",
    "creatinine",
    "esr",
    "crp",
    "hba1c",
    "dlco",
    "fev1",
    "fvc",
    "bilirubin",
    "sgot",
    "sgpt",
)
HISTORY_WORDS = (
    "history of",
    "prior",
    "within",
    "since",
    "previous",
    "past",
    "weeks",
    "months",
    "years",
    "treated with",
    "therapy",
)
MEDICATION_WORDS = (
    "drug",
    "medication",
    "corticosteroid",
    "immunosuppress",
    "antibiotic",
    "anticoagulant",
    "mtx",
    "hcq",
    "ssz",
    "csa",
    "infliximab",
    "adalimumab",
)


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
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


def dump_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def dump_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _norm_text(text: str) -> str:
    return " " + " ".join((text or "").lower().replace("-", " ").split()) + " "


def _contains_any(text: str, keywords: Sequence[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def validate_rule(rule: Dict[str, Any], *, eligibility_text: str) -> Tuple[bool, str]:
    rule_type = str(rule.get("type") or "").strip().upper()
    if rule_type not in ALLOWED_TYPES:
        return False, "invalid_type"

    field = str(rule.get("field") or "").strip().lower()
    if field not in ALLOWED_FIELDS:
        return False, "invalid_field"

    evidence = str(rule.get("evidence_text") or "").strip()
    if not evidence:
        return False, "missing_evidence"

    evidence_norm = _norm_text(evidence)
    if evidence_norm.strip() not in _norm_text(eligibility_text):
        return False, "evidence_not_in_text"

    value = rule.get("value")
    operator = str(rule.get("operator") or "").upper()

    # The primary noise source in raw labels is non-age numeric thresholds mislabeled as age.
    if field == "age":
        if not _contains_any(evidence_norm, AGE_WORDS):
            return False, "age_semantics_mismatch"
        if not isinstance(value, (int, float)):
            return False, "age_non_numeric"
        if value < 0 or value > 120:
            return False, "age_out_of_range"
        if operator and operator not in {">=", "<=", "=", "BETWEEN", ">", "<"}:
            return False, "age_operator_invalid"

    if field == "sex":
        sex_value = str(value or "").lower().strip()
        if sex_value not in {"male", "female", "all"}:
            return False, "sex_value_invalid"
        if not _contains_any(evidence_norm, SEX_WORDS):
            return False, "sex_semantics_mismatch"

    if field == "lab" and not _contains_any(evidence_norm, LAB_WORDS):
        return False, "lab_semantics_mismatch"

    if field == "history" and not _contains_any(evidence_norm, HISTORY_WORDS):
        return False, "history_semantics_mismatch"

    if field == "medication" and not _contains_any(evidence_norm, MEDICATION_WORDS):
        return False, "medication_semantics_mismatch"

    if field == "condition":
        condition_value = str(value or "").lower().strip()
        if not condition_value:
            return False, "condition_value_empty"
        if condition_value.startswith("no ") or condition_value.startswith("not "):
            return False, "condition_negated_value"

    return True, "ok"


def build_dataset(raw_rows: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    by_nct: Dict[str, Dict[str, Any]] = {}
    for row in raw_rows:
        nct_id = str(row.get("nct_id") or "").strip()
        if not nct_id:
            continue
        if nct_id not in by_nct:
            by_nct[nct_id] = row

    output_rows: List[Dict[str, Any]] = []
    dropped_by_reason: Counter[str] = Counter()
    total_rules = 0
    kept_rules = 0

    for nct_id in sorted(by_nct):
        row = by_nct[nct_id]
        eligibility_text = str(row.get("eligibility_text") or "")
        labeled_rules = row.get("labeled_rules")
        if not isinstance(labeled_rules, list):
            labeled_rules = []

        kept: List[Dict[str, Any]] = []
        for rule in labeled_rules:
            if not isinstance(rule, dict):
                dropped_by_reason["rule_not_object"] += 1
                total_rules += 1
                continue
            total_rules += 1
            ok, reason = validate_rule(rule, eligibility_text=eligibility_text)
            if ok:
                kept.append(rule)
                kept_rules += 1
            else:
                dropped_by_reason[reason] += 1

        output_rows.append(
            {
                "nct_id": nct_id,
                "eligibility_text": eligibility_text,
                "labeled_rules": kept,
            }
        )

    manifest = {
        "deduped_trials": len(output_rows),
        "input_rule_count": total_rules,
        "kept_rule_count": kept_rules,
        "dropped_rule_count": total_rules - kept_rules,
        "dropped_by_reason": dict(sorted(dropped_by_reason.items())),
    }
    return output_rows, manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build parsing release dataset with rule-level quality filtering."
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="JSONL source files; repeatable. Default uses archived M4 parsing batches.",
    )
    parser.add_argument("--output-jsonl", default="eval/data/trials_parsing_release.jsonl")
    parser.add_argument(
        "--output-manifest",
        default="eval/data/trials_parsing_release.manifest.json",
    )
    args = parser.parse_args()

    sources = [Path(item) for item in args.source if item.strip()]
    if not sources:
        sources = [
            Path("eval/archive/m4_history/annotations/trials_labeled.batch1.annotator_b.jsonl"),
            Path("eval/archive/m4_history/annotations/trials_labeled.batch2.annotator_b.jsonl"),
        ]

    raw_rows: List[Dict[str, Any]] = []
    for source in sources:
        raw_rows.extend(load_jsonl(source))

    output_rows, manifest = build_dataset(raw_rows)
    manifest["source_files"] = [str(source) for source in sources]
    manifest["source_row_count"] = len(raw_rows)

    dump_jsonl(Path(args.output_jsonl), output_rows)
    dump_json(Path(args.output_manifest), manifest)
    print(json.dumps({"output": args.output_jsonl, **manifest}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
