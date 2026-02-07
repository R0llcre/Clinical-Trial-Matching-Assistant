#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple

from compute_parsing_agreement import RuleSig, load_jsonl, rule_signature

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
_DEPRECATED_VALUES = {
    "manual review needed",
    "manual review note",
    "eligibility criterion",
    "study specific condition",
}


def _import_rule_parser():
    repo_root = Path(__file__).resolve().parents[2]
    worker_root = repo_root / "apps" / "worker"
    if str(worker_root) not in sys.path:
        sys.path.insert(0, str(worker_root))
    from services.eligibility_parser import parse_criteria_v1

    return parse_criteria_v1


def _dump_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def _dump_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _contract_issue_counts(rules: Sequence[Dict[str, Any]]) -> Tuple[int, int, Dict[str, int], Dict[str, int]]:
    error_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()

    for rule in rules:
        field = _norm_text(rule.get("field"))
        operator = str(rule.get("operator") or "").strip().upper()
        value = rule.get("value")

        if field not in _ALLOWED_FIELDS:
            error_counts["FIELD_INVALID"] += 1
            continue
        if operator not in _ALLOWED_FIELD_OPERATORS[field]:
            error_counts["FIELD_OPERATOR_INVALID"] += 1

        if field == "lab" and operator in {">=", "<="} and not _is_number(value):
            error_counts["LAB_THRESHOLD_VALUE_INVALID"] += 1
        if field == "other" and operator == "EXISTS" and value is not None:
            warning_counts["OTHER_EXISTS_VALUE_NON_NULL"] += 1

        if _norm_text(value) in _DEPRECATED_VALUES:
            warning_counts["DEPRECATED_VALUE"] += 1

    return (
        sum(error_counts.values()),
        sum(warning_counts.values()),
        dict(sorted(error_counts.items())),
        dict(sorted(warning_counts.items())),
    )


def _rules_by_signature(rules: Sequence[Dict[str, Any]]) -> Dict[RuleSig, Dict[str, Any]]:
    indexed: Dict[RuleSig, Dict[str, Any]] = {}
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        signature = rule_signature(rule)
        if signature not in indexed:
            indexed[signature] = rule
    return indexed


def _score_candidate(
    *,
    fn_by_field: Counter[str],
    fp_by_field: Counter[str],
    contract_errors: int,
    contract_warnings: int,
    critical_fields: Set[str],
) -> float:
    critical_fn = sum(fn_by_field.get(field, 0) for field in critical_fields)
    critical_fp = sum(fp_by_field.get(field, 0) for field in critical_fields)
    total_fn = sum(fn_by_field.values())
    total_fp = sum(fp_by_field.values())
    noncritical_fn = total_fn - critical_fn
    noncritical_fp = total_fp - critical_fp

    score = (
        critical_fn * 10
        + noncritical_fn * 4
        + critical_fp * 2
        + noncritical_fp * 1
        + contract_errors * 6
        + contract_warnings * 2
    )
    if critical_fn > 0:
        score += 3
    if contract_errors > 0:
        score += 2
    if total_fn >= 10:
        score += 2
    return round(float(score), 4)


def analyze_trial(
    *,
    row: Dict[str, Any],
    predicted_rules: Sequence[Dict[str, Any]],
    critical_fields: Set[str],
    max_diff_rules: int,
) -> Dict[str, Any]:
    nct_id = str(row.get("nct_id") or "").strip()
    eligibility_text = str(row.get("eligibility_text") or "")
    labeled_rules = [rule for rule in row.get("labeled_rules", []) if isinstance(rule, dict)]
    gold_index = _rules_by_signature(labeled_rules)
    pred_index = _rules_by_signature(predicted_rules)

    gold_set = set(gold_index.keys())
    pred_set = set(pred_index.keys())
    fn_signatures = sorted(gold_set - pred_set)
    fp_signatures = sorted(pred_set - gold_set)

    fn_by_field: Counter[str] = Counter(signature[1] for signature in fn_signatures)
    fp_by_field: Counter[str] = Counter(signature[1] for signature in fp_signatures)
    contract_errors, contract_warnings, error_counts, warning_counts = _contract_issue_counts(
        labeled_rules
    )

    score = _score_candidate(
        fn_by_field=fn_by_field,
        fp_by_field=fp_by_field,
        contract_errors=contract_errors,
        contract_warnings=contract_warnings,
        critical_fields=critical_fields,
    )

    focus_fields = sorted(
        {
            *[field for field, count in fn_by_field.items() if count > 0],
            *[field for field, count in fp_by_field.items() if count > 0],
        },
        key=lambda field: (
            -fn_by_field.get(field, 0),
            -fp_by_field.get(field, 0),
            field,
        ),
    )

    reasons: List[str] = []
    critical_fn = sum(fn_by_field.get(field, 0) for field in critical_fields)
    if critical_fn > 0:
        reasons.append(f"missing_critical_rules={critical_fn}")
    if contract_errors > 0:
        reasons.append(f"contract_errors={contract_errors}")
    if contract_warnings > 0:
        reasons.append(f"contract_warnings={contract_warnings}")
    if sum(fn_by_field.values()) > 0:
        reasons.append(f"rule_v1_missing={sum(fn_by_field.values())}")
    if sum(fp_by_field.values()) > 0:
        reasons.append(f"rule_v1_extra={sum(fp_by_field.values())}")

    fn_rules = [gold_index[signature] for signature in fn_signatures[:max_diff_rules]]
    fp_rules = [pred_index[signature] for signature in fp_signatures[:max_diff_rules]]

    return {
        "nct_id": nct_id,
        "eligibility_text": eligibility_text,
        "current_labeled_rules": labeled_rules,
        "priority_score": score,
        "priority_breakdown": {
            "missing_rules_by_field": dict(sorted(fn_by_field.items())),
            "extra_rules_by_field": dict(sorted(fp_by_field.items())),
            "contract_error_count": contract_errors,
            "contract_warning_count": contract_warnings,
            "contract_error_codes": error_counts,
            "contract_warning_codes": warning_counts,
        },
        "focus_fields": focus_fields,
        "priority_reasons": reasons,
        "rule_v1_missing_rules": fn_rules,
        "rule_v1_extra_rules": fp_rules,
    }


def build_relabel_tasks(
    *,
    rows: Sequence[Dict[str, Any]],
    predicted_by_nct: Dict[str, List[Dict[str, Any]]],
    target_trials: int,
    task_id_prefix: str,
    guideline_version: str,
    critical_fields: Set[str],
    max_diff_rules: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if target_trials < 1:
        raise ValueError("target_trials must be >= 1")
    if not task_id_prefix.strip():
        raise ValueError("task_id_prefix must not be empty")
    if max_diff_rules < 1:
        raise ValueError("max_diff_rules must be >= 1")

    candidates: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        nct_id = str(row.get("nct_id") or "").strip()
        if not nct_id:
            continue
        candidate = analyze_trial(
            row=row,
            predicted_rules=predicted_by_nct.get(nct_id, []),
            critical_fields=critical_fields,
            max_diff_rules=max_diff_rules,
        )
        existing = candidates.get(nct_id)
        if existing is None or candidate["priority_score"] > existing["priority_score"]:
            candidates[nct_id] = candidate

    ranked = sorted(
        candidates.values(),
        key=lambda item: (
            -float(item["priority_score"]),
            -sum(item["priority_breakdown"]["missing_rules_by_field"].values()),
            -item["priority_breakdown"]["contract_error_count"],
            item["nct_id"],
        ),
    )

    selected = ranked[:target_trials]
    out_rows: List[Dict[str, Any]] = []
    for idx, row in enumerate(selected, start=1):
        out_rows.append(
            {
                "task_id": f"{task_id_prefix}-{idx:05d}",
                "nct_id": row["nct_id"],
                "status": "PENDING",
                "task_type": "parsing_relabel",
                "guideline_version": guideline_version,
                "priority_score": row["priority_score"],
                "priority_reasons": row["priority_reasons"],
                "priority_breakdown": row["priority_breakdown"],
                "focus_fields": row["focus_fields"],
                "eligibility_text": row["eligibility_text"],
                "current_labeled_rules": row["current_labeled_rules"],
                "rule_v1_missing_rules": row["rule_v1_missing_rules"],
                "rule_v1_extra_rules": row["rule_v1_extra_rules"],
                "instructions": (
                    "Re-label this trial using eligibility_text only. "
                    "Enforce parsing contract v2 and avoid placeholder values."
                ),
            }
        )

    scores = [float(row["priority_score"]) for row in selected]
    manifest = {
        "candidate_trials": len(ranked),
        "selected_trials": len(out_rows),
        "requested_trials": target_trials,
        "shortfall": max(target_trials - len(out_rows), 0),
        "critical_fields": sorted(critical_fields),
        "score_summary": {
            "min": min(scores) if scores else 0.0,
            "median": round(median(scores), 4) if scores else 0.0,
            "mean": round(mean(scores), 4) if scores else 0.0,
            "max": max(scores) if scores else 0.0,
        },
    }
    return out_rows, manifest


def _parse_critical_fields(raw: str) -> Set[str]:
    items = {_norm_text(item) for item in raw.split(",") if item.strip()}
    fields = {item for item in items if item in _ALLOWED_FIELDS}
    if not fields:
        raise ValueError("critical_fields must include at least one valid field")
    return fields


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate high-impact parsing re-label tasks for annotator A/B.",
    )
    parser.add_argument(
        "--trials",
        action="append",
        default=[],
        help="Input trials jsonl. Can pass multiple times.",
    )
    parser.add_argument("--target-trials", type=int, default=120)
    parser.add_argument("--task-id-prefix", default="parsing-relabel-r1")
    parser.add_argument("--guideline-version", default="m5-v1")
    parser.add_argument(
        "--critical-fields",
        default="history,medication,procedure,lab,other",
    )
    parser.add_argument(
        "--max-diff-rules",
        type=int,
        default=30,
        help="Max diff rules embedded per side (missing/extra).",
    )
    parser.add_argument(
        "--output-annotator-a",
        default="eval/annotation_tasks/parsing.relabel.round1.annotator_a.jsonl",
    )
    parser.add_argument(
        "--output-annotator-b",
        default="eval/annotation_tasks/parsing.relabel.round1.annotator_b.jsonl",
    )
    parser.add_argument(
        "--output-manifest",
        default="eval/annotation_tasks/manifest.parsing_relabel_round1.json",
    )
    args = parser.parse_args()

    trials_paths = args.trials or [
        "eval/data/trials_parsing_release.jsonl",
        "eval/data/trials_parsing_blind.jsonl",
    ]
    rows: List[Dict[str, Any]] = []
    for path in trials_paths:
        rows.extend(load_jsonl(Path(path)))

    parse_criteria_v1 = _import_rule_parser()
    predicted_by_nct: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        nct_id = str(row.get("nct_id") or "").strip()
        if not nct_id or nct_id in predicted_by_nct:
            continue
        predicted_by_nct[nct_id] = parse_criteria_v1(str(row.get("eligibility_text") or ""))

    critical_fields = _parse_critical_fields(args.critical_fields)
    tasks, task_manifest = build_relabel_tasks(
        rows=rows,
        predicted_by_nct=predicted_by_nct,
        target_trials=args.target_trials,
        task_id_prefix=args.task_id_prefix,
        guideline_version=args.guideline_version,
        critical_fields=critical_fields,
        max_diff_rules=args.max_diff_rules,
    )

    tasks_a = [dict(task, target_annotator="annotator_a") for task in tasks]
    tasks_b = [dict(task, target_annotator="annotator_b") for task in tasks]

    output_a = Path(args.output_annotator_a)
    output_b = Path(args.output_annotator_b)
    output_manifest = Path(args.output_manifest)
    _dump_jsonl(output_a, tasks_a)
    _dump_jsonl(output_b, tasks_b)

    manifest = {
        "source_trials": trials_paths,
        "guideline_version": args.guideline_version,
        "task_id_prefix": args.task_id_prefix,
        "task_manifest": task_manifest,
        "output_annotator_a": str(output_a),
        "output_annotator_b": str(output_b),
    }
    _dump_json(output_manifest, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
