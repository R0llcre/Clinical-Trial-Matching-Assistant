#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple


RuleSig = Tuple[str, str, str, str, str]


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


def _norm_text(text: Any) -> str:
    return " ".join(str(text or "").lower().replace("-", " ").split())


def _norm_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)
    text = _norm_text(value)
    try:
        float_value = float(text)
    except ValueError:
        return text
    if float_value.is_integer():
        return str(int(float_value))
    return str(float_value)


def rule_signature(rule: Dict[str, Any]) -> RuleSig:
    return (
        str(rule.get("type") or "").strip().upper(),
        _norm_text(rule.get("field") or ""),
        str(rule.get("operator") or "").strip().upper(),
        _norm_value(rule.get("value")),
        _norm_text(rule.get("unit") or ""),
    )


def index_rules_by_nct(rows: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for idx, row in enumerate(rows, start=1):
        nct_id = str(row.get("nct_id") or "").strip()
        if not nct_id:
            raise ValueError(f"rows[{idx}] missing nct_id")
        if nct_id in out:
            raise ValueError(f"duplicate nct_id: {nct_id}")

        rules = row.get("labeled_rules")
        if not isinstance(rules, list):
            raise ValueError(f"rows[{idx}] labeled_rules must be a list")

        signatures: set[RuleSig] = set()
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            signatures.add(rule_signature(rule))

        out[nct_id] = {
            "eligibility_text": str(row.get("eligibility_text") or ""),
            "rule_set": signatures,
            "rule_count_raw": len([item for item in rules if isinstance(item, dict)]),
        }
    return out


def compute_agreement(
    a_index: Dict[str, Dict[str, Any]],
    b_index: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    keys_a = set(a_index.keys())
    keys_b = set(b_index.keys())
    if keys_a != keys_b:
        only_a = sorted(keys_a - keys_b)
        only_b = sorted(keys_b - keys_a)
        raise ValueError(
            "nct_id mismatch between files: "
            f"only_in_a={len(only_a)}, only_in_b={len(only_b)}"
        )

    total_tp = 0
    total_fp = 0
    total_fn = 0
    jaccards: List[float] = []
    mismatch_rows: List[Dict[str, Any]] = []
    exact_trial_matches = 0

    for nct_id in sorted(keys_a):
        a_set = a_index[nct_id]["rule_set"]
        b_set = b_index[nct_id]["rule_set"]
        shared = a_set & b_set
        only_a = a_set - b_set
        only_b = b_set - a_set
        union = a_set | b_set
        jaccard = (len(shared) / len(union)) if union else 1.0

        total_tp += len(shared)
        total_fp += len(only_b)
        total_fn += len(only_a)
        jaccards.append(jaccard)

        if not only_a and not only_b:
            exact_trial_matches += 1
            continue
        mismatch_rows.append(
            {
                "nct_id": nct_id,
                "jaccard": round(jaccard, 4),
                "shared_rule_count": len(shared),
                "a_only_rule_count": len(only_a),
                "b_only_rule_count": len(only_b),
                "a_rule_count_raw": int(a_index[nct_id]["rule_count_raw"]),
                "b_rule_count_raw": int(b_index[nct_id]["rule_count_raw"]),
            }
        )

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    summary = {
        "trial_count": len(keys_a),
        "exact_trial_match_count": exact_trial_matches,
        "exact_trial_match_rate": round(exact_trial_matches / len(keys_a), 4) if keys_a else 0.0,
        "rule_set_precision": round(precision, 4),
        "rule_set_recall": round(recall, 4),
        "rule_set_f1": round(f1, 4),
        "tp": total_tp,
        "fp": total_fp,
        "fn": total_fn,
        "mismatch_trial_count": len(mismatch_rows),
        "avg_jaccard": round(sum(jaccards) / len(jaccards), 4) if jaccards else 0.0,
        "median_jaccard": round(statistics.median(jaccards), 4) if jaccards else 0.0,
        "min_jaccard": round(min(jaccards), 4) if jaccards else 0.0,
        "max_jaccard": round(max(jaccards), 4) if jaccards else 0.0,
    }
    return summary, mismatch_rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute agreement metrics for parsing blind annotations."
    )
    parser.add_argument("--a", required=True)
    parser.add_argument("--b", required=True)
    parser.add_argument("--output-json", default="")
    parser.add_argument("--mismatches-out", default="")
    args = parser.parse_args()

    a_index = index_rules_by_nct(load_jsonl(Path(args.a)))
    b_index = index_rules_by_nct(load_jsonl(Path(args.b)))
    summary, mismatches = compute_agreement(a_index, b_index)

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.mismatches_out:
        dump_jsonl(Path(args.mismatches_out), mismatches)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
