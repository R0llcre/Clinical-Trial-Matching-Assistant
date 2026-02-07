#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple


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


def load_release_nct_ids(path: Path) -> Set[str]:
    rows = load_jsonl(path)
    nct_ids: Set[str] = set()
    for row in rows:
        nct_id = str(row.get("nct_id") or "").strip()
        if nct_id:
            nct_ids.add(nct_id)
    return nct_ids


def build_blind_candidates(
    pending_rows: Sequence[Dict[str, Any]],
    *,
    release_nct_ids: Set[str],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    excluded_overlap = 0
    invalid_rows = 0

    for row in pending_rows:
        nct_id = str(row.get("nct_id") or "").strip()
        if not nct_id:
            invalid_rows += 1
            continue
        if nct_id in release_nct_ids:
            excluded_overlap += 1
            continue

        support_raw = row.get("query_support_count", 0)
        try:
            support_count = int(support_raw)
        except (TypeError, ValueError):
            support_count = 0

        candidate = {
            "nct_id": nct_id,
            "query_support_count": max(support_count, 0),
        }
        existing = deduped.get(nct_id)
        if existing is None or candidate["query_support_count"] > existing["query_support_count"]:
            deduped[nct_id] = candidate

    candidates = sorted(
        deduped.values(),
        key=lambda item: (-int(item["query_support_count"]), str(item["nct_id"])),
    )

    manifest = {
        "input_rows": len(pending_rows),
        "invalid_rows": invalid_rows,
        "excluded_release_overlap_rows": excluded_overlap,
        "unique_candidates": len(candidates),
    }
    return candidates, manifest


def build_blind_tasks(
    candidates: Sequence[Dict[str, Any]],
    *,
    target_trials: int,
    task_id_prefix: str,
    guideline_version: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if target_trials < 1:
        raise ValueError("target_trials must be >= 1")
    if not task_id_prefix.strip():
        raise ValueError("task_id_prefix must not be empty")

    selected = list(candidates[:target_trials])
    tasks: List[Dict[str, Any]] = []
    for idx, row in enumerate(selected, start=1):
        tasks.append(
            {
                "task_id": f"{task_id_prefix}-{idx:05d}",
                "nct_id": row["nct_id"],
                "query_support_count": int(row["query_support_count"]),
                "status": "PENDING",
                "task_type": "rule_annotation",
                "guideline_version": guideline_version,
                "notes": (
                    "Blind parsing annotation: fetch trial details by nct_id, "
                    "annotate labeled_rules only from eligibility_text, "
                    "do not consult release labels."
                ),
            }
        )

    supports = [int(item["query_support_count"]) for item in selected]
    support_summary = {
        "min": min(supports) if supports else 0,
        "max": max(supports) if supports else 0,
        "avg": round(sum(supports) / len(supports), 4) if supports else 0.0,
    }

    manifest = {
        "requested_trials": target_trials,
        "selected_trials": len(tasks),
        "shortfall": max(target_trials - len(tasks), 0),
        "support_summary": support_summary,
    }
    return tasks, manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate blind parsing annotation tasks excluding release trials."
    )
    parser.add_argument(
        "--pending",
        default="eval/archive/m4_history/annotation_tasks/parsing.pending.200.jsonl",
    )
    parser.add_argument(
        "--release-trials",
        default="eval/data/trials_parsing_release.jsonl",
    )
    parser.add_argument("--target-trials", type=int, default=60)
    parser.add_argument("--task-id-prefix", default="parsing-blind-r1")
    parser.add_argument("--guideline-version", default="m4-v1")
    parser.add_argument(
        "--output-annotator-a",
        default="eval/annotation_tasks/parsing.blind.round1.annotator_a.jsonl",
    )
    parser.add_argument(
        "--output-annotator-b",
        default="eval/annotation_tasks/parsing.blind.round1.annotator_b.jsonl",
    )
    parser.add_argument(
        "--output-manifest",
        default="eval/annotation_tasks/manifest.parsing_blind_round1.json",
    )
    args = parser.parse_args()

    pending_rows = load_jsonl(Path(args.pending))
    release_nct_ids = load_release_nct_ids(Path(args.release_trials))
    candidates, candidate_manifest = build_blind_candidates(
        pending_rows,
        release_nct_ids=release_nct_ids,
    )
    tasks, task_manifest = build_blind_tasks(
        candidates,
        target_trials=args.target_trials,
        task_id_prefix=args.task_id_prefix,
        guideline_version=args.guideline_version,
    )

    output_a = Path(args.output_annotator_a)
    output_b = Path(args.output_annotator_b)
    output_manifest = Path(args.output_manifest)

    dump_jsonl(output_a, tasks)
    dump_jsonl(output_b, tasks)

    manifest = {
        "source_pending": args.pending,
        "source_release_trials": args.release_trials,
        "target_trials": args.target_trials,
        "guideline_version": args.guideline_version,
        "task_id_prefix": args.task_id_prefix,
        "candidate_manifest": candidate_manifest,
        "task_manifest": task_manifest,
        "output_annotator_a": str(output_a),
        "output_annotator_b": str(output_b),
    }
    dump_json(output_manifest, manifest)

    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
