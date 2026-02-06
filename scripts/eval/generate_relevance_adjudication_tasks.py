#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple


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


def load_task_ids(path: Path) -> set[str]:
    ids: set[str] = set()
    if not path.exists():
        return ids
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            token = line.strip().strip(",")
            if not token:
                continue
            ids.add(token)
    return ids


def _pair_key(row: Dict[str, Any]) -> Tuple[str, str]:
    return (
        str(row.get("query_id") or "").strip(),
        str(row.get("nct_id") or "").strip(),
    )


def _validate_rows(labels: Sequence[Dict[str, Any]], tasks: Sequence[Dict[str, Any]]) -> None:
    for idx, row in enumerate(labels, start=1):
        query_id, nct_id = _pair_key(row)
        if not query_id or not nct_id:
            raise ValueError(f"labels[{idx}] missing query_id/nct_id")
        label = row.get("relevance_label")
        if isinstance(label, bool) or not isinstance(label, int) or label not in {0, 1, 2}:
            raise ValueError(f"labels[{idx}] invalid relevance_label: {label}")

    for idx, row in enumerate(tasks, start=1):
        query_id, nct_id = _pair_key(row)
        if not query_id or not nct_id:
            raise ValueError(f"tasks[{idx}] missing query_id/nct_id")
        task_id = str(row.get("task_id") or "").strip()
        if not task_id:
            raise ValueError(f"tasks[{idx}] missing task_id")


def build_adjudication_tasks(
    *,
    labels: Sequence[Dict[str, Any]],
    tasks: Sequence[Dict[str, Any]],
    ambiguous_task_ids: set[str],
    likely2_label1_per_query: int = 15,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if likely2_label1_per_query < 0:
        raise ValueError("likely2_label1_per_query must be >= 0")

    _validate_rows(labels, tasks)
    task_by_pair = {_pair_key(row): row for row in tasks}

    joined: List[Dict[str, Any]] = []
    missing_task_meta = 0
    for label_row in labels:
        pair = _pair_key(label_row)
        task_row = task_by_pair.get(pair)
        if task_row is None:
            missing_task_meta += 1
            continue
        merged = {
            **label_row,
            "_task_id": str(task_row.get("task_id") or "").strip(),
            "_task_band": str(task_row.get("band") or "").strip(),
            "_heuristic_score": float(task_row.get("heuristic_score") or 0.0),
        }
        joined.append(merged)

    selected: Dict[Tuple[str, str], Dict[str, Any]] = {}
    reason_counts: Counter[str] = Counter()

    def add_row(row: Dict[str, Any], reason: str) -> None:
        key = _pair_key(row)
        if not key[0] or not key[1]:
            return
        if key not in selected:
            selected[key] = {
                "query_id": key[0],
                "nct_id": key[1],
                "source_task_id": row["_task_id"],
                "source_band": row["_task_band"] or None,
                "heuristic_score": round(float(row["_heuristic_score"]), 4),
                "relevance_label_b": int(row["relevance_label"]),
                "rationale_b": str(row.get("rationale") or "").strip(),
                "selection_reasons": [],
                "status": "PENDING",
                "target_annotator": "annotator_a",
                "guideline_version": "m4-v1",
            }
        if reason not in selected[key]["selection_reasons"]:
            selected[key]["selection_reasons"].append(reason)
            reason_counts[reason] += 1

    # 1) Include all label=2 rows.
    for row in joined:
        if int(row["relevance_label"]) == 2:
            add_row(row, "label_2")

    # 2) Include all explicitly ambiguous task_ids.
    if ambiguous_task_ids:
        for row in joined:
            if row["_task_id"] in ambiguous_task_ids:
                add_row(row, "annotator_ambiguous")

    # 3) Include likely_2 but labeled as 1 (calibration candidates), capped per query.
    by_query: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in joined:
        if int(row["relevance_label"]) != 1:
            continue
        if row["_task_band"] != "likely_2":
            continue
        by_query[str(row["query_id"])].append(row)

    for query_id in sorted(by_query):
        candidates = sorted(
            by_query[query_id],
            key=lambda item: (-float(item["_heuristic_score"]), str(item["_task_id"])),
        )
        for row in candidates[:likely2_label1_per_query]:
            add_row(row, "likely2_labeled1")

    out_rows = sorted(
        selected.values(),
        key=lambda item: (
            str(item["query_id"]),
            str(item.get("source_task_id") or ""),
            str(item["nct_id"]),
        ),
    )
    for idx, row in enumerate(out_rows, start=1):
        row["adjudication_id"] = f"adj-{idx:05d}"

    selected_by_query: Dict[str, int] = defaultdict(int)
    for row in out_rows:
        selected_by_query[str(row["query_id"])] += 1

    manifest = {
        "input_label_rows": len(labels),
        "input_task_rows": len(tasks),
        "missing_task_metadata_rows": missing_task_meta,
        "selected_rows": len(out_rows),
        "selected_by_reason": dict(sorted(reason_counts.items())),
        "selected_by_query": dict(sorted(selected_by_query.items())),
        "likely2_label1_per_query": likely2_label1_per_query,
        "ambiguous_task_id_count": len(ambiguous_task_ids),
    }
    return out_rows, manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate adjudication tasks for relevance labels (annotator_a review)."
    )
    parser.add_argument(
        "--labels",
        default="eval/annotations/relevance.v2.round1.annotator_b.jsonl",
        help="Label file from annotator_b",
    )
    parser.add_argument(
        "--tasks",
        default="eval/annotation_tasks/relevance.batch_v2_round1.700.jsonl",
        help="Original task file containing task_id/band/score",
    )
    parser.add_argument(
        "--ambiguous-task-ids",
        default="",
        help="Optional txt file with one task_id per line",
    )
    parser.add_argument(
        "--likely2-label1-per-query",
        type=int,
        default=15,
    )
    parser.add_argument(
        "--output-jsonl",
        default="eval/annotation_tasks/relevance.v2.round1.adjudication.annotator_a.jsonl",
    )
    parser.add_argument(
        "--output-manifest",
        default="eval/annotation_tasks/manifest.relevance.v2.round1.adjudication.json",
    )
    args = parser.parse_args()

    labels = load_jsonl(Path(args.labels))
    tasks = load_jsonl(Path(args.tasks))
    ambiguous_task_ids = set()
    if args.ambiguous_task_ids:
        ambiguous_task_ids = load_task_ids(Path(args.ambiguous_task_ids))

    out_rows, manifest = build_adjudication_tasks(
        labels=labels,
        tasks=tasks,
        ambiguous_task_ids=ambiguous_task_ids,
        likely2_label1_per_query=args.likely2_label1_per_query,
    )

    dump_jsonl(Path(args.output_jsonl), out_rows)
    dump_json(Path(args.output_manifest), manifest)
    print(json.dumps({"output": args.output_jsonl, **manifest}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
