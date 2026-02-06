#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from compute_parsing_agreement import index_rules_by_nct, load_jsonl, rule_signature

RuleSig = Tuple[str, str, str, str, str]


def dump_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def dump_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _index_original_rules(rows: Sequence[Dict[str, Any]]) -> Dict[str, Dict[RuleSig, Dict[str, Any]]]:
    out: Dict[str, Dict[RuleSig, Dict[str, Any]]] = {}
    for row in rows:
        nct_id = str(row.get("nct_id") or "").strip()
        if not nct_id:
            continue
        rules = row.get("labeled_rules")
        if not isinstance(rules, list):
            continue
        bucket: Dict[RuleSig, Dict[str, Any]] = {}
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            signature = rule_signature(rule)
            if signature not in bucket:
                bucket[signature] = rule
        out[nct_id] = bucket
    return out


def _sorted_rules_from_signatures(
    signatures: Iterable[RuleSig],
    original_map: Dict[RuleSig, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for signature in sorted(set(signatures)):
        rule = original_map.get(signature)
        if rule is None:
            rows.append(
                {
                    "type": signature[0],
                    "field": signature[1],
                    "operator": signature[2],
                    "value": signature[3],
                    "unit": signature[4] or None,
                    "evidence_text": "",
                }
            )
        else:
            rows.append(rule)
    return rows


def build_parsing_adjudication_tasks(
    *,
    a_rows: Sequence[Dict[str, Any]],
    b_rows: Sequence[Dict[str, Any]],
    guideline_version: str = "m4-v1",
    max_trials: int = 0,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    a_index = index_rules_by_nct(a_rows)
    b_index = index_rules_by_nct(b_rows)
    keys_a = set(a_index.keys())
    keys_b = set(b_index.keys())
    if keys_a != keys_b:
        only_a = sorted(keys_a - keys_b)
        only_b = sorted(keys_b - keys_a)
        raise ValueError(
            "nct_id mismatch between files: "
            f"only_in_a={len(only_a)}, only_in_b={len(only_b)}"
        )

    a_original = _index_original_rules(a_rows)
    b_original = _index_original_rules(b_rows)

    candidates: List[Dict[str, Any]] = []
    for nct_id in sorted(keys_a):
        a_set = a_index[nct_id]["rule_set"]
        b_set = b_index[nct_id]["rule_set"]
        shared = a_set & b_set
        only_a = a_set - b_set
        only_b = b_set - a_set
        if not only_a and not only_b:
            continue

        union = a_set | b_set
        jaccard = (len(shared) / len(union)) if union else 1.0
        a_text = str(a_index[nct_id]["eligibility_text"] or "")
        b_text = str(b_index[nct_id]["eligibility_text"] or "")

        candidates.append(
            {
                "nct_id": nct_id,
                "eligibility_text": a_text if a_text else b_text,
                "shared_rule_count": len(shared),
                "a_only_rule_count": len(only_a),
                "b_only_rule_count": len(only_b),
                "jaccard": round(jaccard, 4),
                "shared_rules": _sorted_rules_from_signatures(shared, a_original.get(nct_id, {})),
                "a_only_rules": _sorted_rules_from_signatures(only_a, a_original.get(nct_id, {})),
                "b_only_rules": _sorted_rules_from_signatures(only_b, b_original.get(nct_id, {})),
            }
        )

    ranked = sorted(
        candidates,
        key=lambda item: (
            float(item["jaccard"]),
            -int(item["a_only_rule_count"] + item["b_only_rule_count"]),
            str(item["nct_id"]),
        ),
    )
    if max_trials > 0:
        ranked = ranked[:max_trials]

    out_rows: List[Dict[str, Any]] = []
    for idx, row in enumerate(ranked, start=1):
        out_rows.append(
            {
                "adjudication_id": f"parsing-adj-{idx:05d}",
                "nct_id": row["nct_id"],
                "status": "PENDING",
                "task_type": "parsing_adjudication",
                "target_annotator": "annotator_a",
                "guideline_version": guideline_version,
                "jaccard": row["jaccard"],
                "shared_rule_count": row["shared_rule_count"],
                "a_only_rule_count": row["a_only_rule_count"],
                "b_only_rule_count": row["b_only_rule_count"],
                "eligibility_text": row["eligibility_text"],
                "shared_rules": row["shared_rules"],
                "a_only_rules": row["a_only_rules"],
                "b_only_rules": row["b_only_rules"],
                "instructions": (
                    "Review A/B differences for this trial, keep only evidence-supported rules, "
                    "and produce final labeled_rules."
                ),
            }
        )

    manifest = {
        "input_trial_count": len(keys_a),
        "disagreement_trial_count": len(candidates),
        "selected_trial_count": len(out_rows),
        "max_trials": int(max_trials),
        "guideline_version": guideline_version,
    }
    return out_rows, manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate adjudication tasks for parsing blind annotations."
    )
    parser.add_argument(
        "--a",
        default="eval/annotations/trials_parsing_blind.round1.annotator_a.jsonl",
    )
    parser.add_argument(
        "--b",
        default="eval/annotations/trials_parsing_blind.round1.annotator_b.jsonl",
    )
    parser.add_argument("--guideline-version", default="m4-v1")
    parser.add_argument(
        "--max-trials",
        type=int,
        default=0,
        help="0 means include all disagreement trials.",
    )
    parser.add_argument(
        "--output-jsonl",
        default="eval/annotation_tasks/parsing.blind.round1.adjudication.annotator_a.jsonl",
    )
    parser.add_argument(
        "--output-manifest",
        default="eval/annotation_tasks/manifest.parsing_blind_round1.adjudication.json",
    )
    args = parser.parse_args()

    rows, manifest = build_parsing_adjudication_tasks(
        a_rows=load_jsonl(Path(args.a)),
        b_rows=load_jsonl(Path(args.b)),
        guideline_version=args.guideline_version,
        max_trials=args.max_trials,
    )
    dump_jsonl(Path(args.output_jsonl), rows)
    dump_json(Path(args.output_manifest), manifest)
    print(json.dumps({"output": args.output_jsonl, **manifest}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
