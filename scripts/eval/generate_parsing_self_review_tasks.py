#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


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


def _nct_id(row: Dict[str, Any]) -> str:
    return str(row.get("nct_id") or "").strip()


def _is_ambiguous(row: Dict[str, Any]) -> bool:
    value = row.get("ambiguous")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    value = row.get("is_ambiguous")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False


def _rank_disagreements(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def _score(row: Dict[str, Any]) -> tuple[int, float, str]:
        a_only = int(row.get("a_only_rule_count") or 0)
        b_only = int(row.get("b_only_rule_count") or 0)
        total_diff = a_only + b_only
        jaccard = float(row.get("jaccard") or 0.0)
        nct = _nct_id(row)
        return (-total_diff, jaccard, nct)

    return sorted(rows, key=_score)


def build_self_review_tasks(
    *,
    adjudicated_rows: Sequence[Dict[str, Any]],
    disagreement_rows: Sequence[Dict[str, Any]],
    target_trials: int,
    task_id_prefix: str,
    guideline_version: str,
    target_annotator: str,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if target_trials < 1:
        raise ValueError("target_trials must be >= 1")
    if not task_id_prefix.strip():
        raise ValueError("task_id_prefix must not be empty")

    adjudicated_by_nct: Dict[str, Dict[str, Any]] = {}
    for row in adjudicated_rows:
        nct_id = _nct_id(row)
        if not nct_id:
            continue
        adjudicated_by_nct[nct_id] = row

    ranked = _rank_disagreements(disagreement_rows)
    rank_by_nct = {_nct_id(row): idx for idx, row in enumerate(ranked)}

    ambiguous_ids = sorted(
        [nct for nct, row in adjudicated_by_nct.items() if _is_ambiguous(row)],
        key=lambda nct: rank_by_nct.get(nct, 10**9),
    )

    selected_ids: List[str] = []
    seen: set[str] = set()
    for nct_id in ambiguous_ids:
        if nct_id in seen:
            continue
        seen.add(nct_id)
        selected_ids.append(nct_id)
        if len(selected_ids) >= target_trials:
            break

    if len(selected_ids) < target_trials:
        for row in ranked:
            nct_id = _nct_id(row)
            if not nct_id or nct_id in seen or nct_id not in adjudicated_by_nct:
                continue
            seen.add(nct_id)
            selected_ids.append(nct_id)
            if len(selected_ids) >= target_trials:
                break

    if len(selected_ids) < target_trials:
        for nct_id in sorted(adjudicated_by_nct.keys()):
            if nct_id in seen:
                continue
            seen.add(nct_id)
            selected_ids.append(nct_id)
            if len(selected_ids) >= target_trials:
                break

    disagreement_index = {_nct_id(row): row for row in disagreement_rows if _nct_id(row)}
    tasks: List[Dict[str, Any]] = []
    ambiguous_selected = 0
    for idx, nct_id in enumerate(selected_ids, start=1):
        adjudicated = adjudicated_by_nct[nct_id]
        dis = disagreement_index.get(nct_id, {})
        ambiguous = _is_ambiguous(adjudicated)
        if ambiguous:
            ambiguous_selected += 1
        tasks.append(
            {
                "task_id": f"{task_id_prefix}-{idx:05d}",
                "nct_id": nct_id,
                "status": "PENDING",
                "task_type": "parsing_self_review",
                "target_annotator": target_annotator,
                "guideline_version": guideline_version,
                "priority_reason": (
                    "ambiguous_from_round1" if ambiguous else "high_disagreement_backfill"
                ),
                "jaccard": float(dis.get("jaccard") or 0.0),
                "a_only_rule_count": int(dis.get("a_only_rule_count") or 0),
                "b_only_rule_count": int(dis.get("b_only_rule_count") or 0),
                "eligibility_text": str(adjudicated.get("eligibility_text") or ""),
                "labeled_rules": [
                    rule for rule in adjudicated.get("labeled_rules", []) if isinstance(rule, dict)
                ],
                "instructions": (
                    "Self-review round2: re-check all labeled_rules against eligibility_text, "
                    "keep only evidence-supported rules, and ensure parsing contract compliance."
                ),
            }
        )

    manifest = {
        "adjudicated_trials": len(adjudicated_by_nct),
        "disagreement_trials": len(disagreement_rows),
        "ambiguous_trials_available": len(ambiguous_ids),
        "selected_trials": len(tasks),
        "requested_trials": target_trials,
        "shortfall": max(target_trials - len(tasks), 0),
        "selected_ambiguous_trials": ambiguous_selected,
        "selected_backfill_trials": len(tasks) - ambiguous_selected,
        "target_annotator": target_annotator,
        "guideline_version": guideline_version,
    }
    return tasks, manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate parsing round2 self-review tasks from adjudicated round1 output."
    )
    parser.add_argument(
        "--adjudicated",
        required=True,
        help="Round1 adjudicated parsing labels JSONL.",
    )
    parser.add_argument(
        "--disagreements",
        required=True,
        help="Round1 disagreement task JSONL with jaccard/a_only/b_only fields.",
    )
    parser.add_argument("--target-trials", type=int, default=60)
    parser.add_argument("--task-id-prefix", default="parsing-relabel-r2-self")
    parser.add_argument("--guideline-version", default="m5-v1")
    parser.add_argument("--target-annotator", default="annotator_c")
    parser.add_argument(
        "--output-jsonl",
        default="eval/annotation_tasks/parsing.relabel.round2.self_review.annotator_c.jsonl",
    )
    parser.add_argument(
        "--output-manifest",
        default="eval/annotation_tasks/manifest.parsing_relabel_round2.self_review.json",
    )
    args = parser.parse_args()

    tasks, manifest = build_self_review_tasks(
        adjudicated_rows=load_jsonl(Path(args.adjudicated)),
        disagreement_rows=load_jsonl(Path(args.disagreements)),
        target_trials=args.target_trials,
        task_id_prefix=args.task_id_prefix,
        guideline_version=args.guideline_version,
        target_annotator=args.target_annotator,
    )
    dump_jsonl(Path(args.output_jsonl), tasks)
    dump_json(Path(args.output_manifest), manifest)
    print(json.dumps({"output": args.output_jsonl, **manifest}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
