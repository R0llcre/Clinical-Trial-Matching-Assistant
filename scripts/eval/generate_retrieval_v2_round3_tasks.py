#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

VALID_LABELS = {0, 1, 2}
VALID_BANDS = ("likely_2", "likely_1", "hard_negative")
BLIND_FIELDS = (
    "task_id",
    "task_type",
    "status",
    "guideline_version",
    "query_id",
    "nct_id",
    "title",
    "overall_status",
    "phases",
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


def _pair_key(row: Dict[str, Any]) -> Tuple[str, str]:
    return (
        str(row.get("query_id") or "").strip(),
        str(row.get("nct_id") or "").strip(),
    )


def load_excluded_pairs(paths: Sequence[Path]) -> set[Tuple[str, str]]:
    excluded: set[Tuple[str, str]] = set()
    for path in paths:
        if not path.exists():
            continue
        for row in load_jsonl(path):
            query_id, nct_id = _pair_key(row)
            if query_id and nct_id:
                excluded.add((query_id, nct_id))
    return excluded


def compute_label2_counts(reference_rows: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for idx, row in enumerate(reference_rows, start=1):
        query_id, nct_id = _pair_key(row)
        if not query_id or not nct_id:
            raise ValueError(f"reference[{idx}] missing query_id or nct_id")
        label = row.get("relevance_label")
        if isinstance(label, bool) or not isinstance(label, int) or label not in VALID_LABELS:
            raise ValueError(f"reference[{idx}] invalid relevance_label: {label}")
        if int(label) == 2:
            counts[query_id] += 1
    return dict(counts)


def determine_focus_queries(
    *,
    pending_rows: Sequence[Dict[str, Any]],
    reference_rows: Sequence[Dict[str, Any]],
    max_label2_count: int,
    explicit_focus_queries: Sequence[str],
) -> Tuple[List[str], Dict[str, int]]:
    if max_label2_count < 0:
        raise ValueError("max_label2_count must be >= 0")

    pending_queries = sorted({str(row.get("query_id") or "").strip() for row in pending_rows if row})
    pending_queries = [query_id for query_id in pending_queries if query_id]
    label2_counts = compute_label2_counts(reference_rows)

    if explicit_focus_queries:
        requested = [item.strip() for item in explicit_focus_queries if item.strip()]
        missing = [query_id for query_id in requested if query_id not in pending_queries]
        if missing:
            raise ValueError(f"focus queries absent from pending rows: {missing}")
        return requested, label2_counts

    focus = [query_id for query_id in pending_queries if label2_counts.get(query_id, 0) <= max_label2_count]
    return focus, label2_counts


def _sort_candidates(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            -float(row.get("heuristic_score") or 0.0),
            str(row.get("nct_id") or ""),
        ),
    )


def build_targeted_batch(
    *,
    pending_rows: Sequence[Dict[str, Any]],
    reference_rows: Sequence[Dict[str, Any]],
    excluded_pairs: set[Tuple[str, str]],
    focus_queries: Sequence[str],
    label2_counts: Dict[str, int],
    target_per_query: int,
    likely2_quota: int,
    likely1_quota: int,
    hard_negative_quota: int,
    task_id_prefix: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if target_per_query < 1:
        raise ValueError("target_per_query must be >= 1")
    if likely2_quota < 0 or likely1_quota < 0 or hard_negative_quota < 0:
        raise ValueError("band quotas must be >= 0")
    if not task_id_prefix.strip():
        raise ValueError("task_id_prefix must be non-empty")

    reference_pair_count = len({_pair_key(row) for row in reference_rows if _pair_key(row) != ("", "")})
    by_query: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    deduped_pending = 0

    seen_pairs: set[Tuple[str, str]] = set()
    for row in _sort_candidates(pending_rows):
        query_id, nct_id = _pair_key(row)
        if not query_id or not nct_id:
            continue
        pair = (query_id, nct_id)
        if pair in excluded_pairs or pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        deduped_pending += 1
        if query_id in focus_queries:
            candidate = dict(row)
            band = str(candidate.get("band") or "hard_negative")
            if band not in VALID_BANDS:
                candidate["band"] = "hard_negative"
            by_query[query_id].append(candidate)

    selected: List[Dict[str, Any]] = []
    query_summary: Dict[str, Any] = {}
    quota_map = {
        "likely_2": likely2_quota,
        "likely_1": likely1_quota,
        "hard_negative": hard_negative_quota,
    }

    for query_id in focus_queries:
        pool = by_query.get(query_id, [])
        by_band: Dict[str, List[Dict[str, Any]]] = {
            "likely_2": [],
            "likely_1": [],
            "hard_negative": [],
        }
        for row in pool:
            by_band[str(row.get("band") or "hard_negative")].append(row)
        for band in VALID_BANDS:
            by_band[band] = _sort_candidates(by_band[band])

        picked: List[Dict[str, Any]] = []
        for band in VALID_BANDS:
            take = min(quota_map[band], len(by_band[band]))
            picked.extend(by_band[band][:take])
            by_band[band] = by_band[band][take:]

        remaining_slots = max(target_per_query - len(picked), 0)
        fallback = by_band["likely_2"] + by_band["likely_1"] + by_band["hard_negative"]
        picked.extend(fallback[:remaining_slots])
        picked = _sort_candidates(picked)[:target_per_query]

        picked_counts: Dict[str, int] = defaultdict(int)
        for row in picked:
            picked_counts[str(row.get("band") or "hard_negative")] += 1
            selected.append(row)

        query_summary[query_id] = {
            "label2_count_in_reference": label2_counts.get(query_id, 0),
            "available_after_exclusion": len(pool),
            "picked": len(picked),
            "picked_band_counts": dict(sorted(picked_counts.items())),
            "shortfall": max(target_per_query - len(picked), 0),
        }

    selected.sort(
        key=lambda row: (
            str(row.get("query_id") or ""),
            -float(row.get("heuristic_score") or 0.0),
            str(row.get("nct_id") or ""),
        )
    )
    batch_rows: List[Dict[str, Any]] = []
    for idx, row in enumerate(selected, start=1):
        item = dict(row)
        item["task_id"] = f"{task_id_prefix}-{idx:05d}"
        batch_rows.append(item)

    manifest = {
        "input_pending_rows": len(pending_rows),
        "input_reference_rows": reference_pair_count,
        "excluded_pair_count": len(excluded_pairs),
        "deduped_pending_rows_after_exclusion": deduped_pending,
        "focus_queries": list(focus_queries),
        "target_per_query": target_per_query,
        "quotas": {
            "likely_2": likely2_quota,
            "likely_1": likely1_quota,
            "hard_negative": hard_negative_quota,
        },
        "task_id_prefix": task_id_prefix,
        "total_rows": len(batch_rows),
        "query_summary": query_summary,
    }
    return batch_rows, manifest


def build_blind_rows(batch_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for row in batch_rows:
        output.append({field: row[field] for field in BLIND_FIELDS if field in row})
    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate targeted v2 round3 retrieval tasks for label-2 sparse queries."
    )
    parser.add_argument(
        "--pending",
        default="eval/annotation_tasks/relevance.pending.v2.round2.jsonl",
        help="Candidate pending pool",
    )
    parser.add_argument(
        "--reference-labels",
        default="eval/annotations/relevance.v2.round1_round2.final.jsonl",
        help="Reference final labels used to detect sparse queries and exclude duplicates",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Additional JSONL files with query_id/nct_id to exclude",
    )
    parser.add_argument(
        "--focus-query",
        action="append",
        default=[],
        help="Optional explicit focus query_id (repeatable); if omitted auto-select by max_label2_count",
    )
    parser.add_argument("--max-label2-count", type=int, default=0)
    parser.add_argument("--target-per-query", type=int, default=50)
    parser.add_argument("--likely2-quota", type=int, default=35)
    parser.add_argument("--likely1-quota", type=int, default=15)
    parser.add_argument("--hard-negative-quota", type=int, default=0)
    parser.add_argument("--task-id-prefix", default="relevance-v2r3")
    parser.add_argument(
        "--output-batch",
        default="eval/annotation_tasks/relevance.batch_v2_round3.targeted.jsonl",
    )
    parser.add_argument(
        "--output-blind",
        default="eval/annotation_tasks/relevance.batch_v2_round3.targeted.blind.jsonl",
    )
    parser.add_argument(
        "--output-manifest",
        default="eval/annotation_tasks/manifest.relevance_v2_round3.targeted.json",
    )
    args = parser.parse_args()

    pending_rows = load_jsonl(Path(args.pending))
    reference_rows = load_jsonl(Path(args.reference_labels))

    exclude_paths: List[Path] = [Path(args.reference_labels)]
    for item in args.exclude:
        path = Path(item)
        if path not in exclude_paths:
            exclude_paths.append(path)
    excluded_pairs = load_excluded_pairs(exclude_paths)

    focus_queries, label2_counts = determine_focus_queries(
        pending_rows=pending_rows,
        reference_rows=reference_rows,
        max_label2_count=args.max_label2_count,
        explicit_focus_queries=args.focus_query,
    )
    if not focus_queries:
        raise ValueError("no focus queries selected; adjust --max-label2-count or --focus-query")

    batch_rows, manifest = build_targeted_batch(
        pending_rows=pending_rows,
        reference_rows=reference_rows,
        excluded_pairs=excluded_pairs,
        focus_queries=focus_queries,
        label2_counts=label2_counts,
        target_per_query=args.target_per_query,
        likely2_quota=args.likely2_quota,
        likely1_quota=args.likely1_quota,
        hard_negative_quota=args.hard_negative_quota,
        task_id_prefix=args.task_id_prefix,
    )
    blind_rows = build_blind_rows(batch_rows)

    dump_jsonl(Path(args.output_batch), batch_rows)
    dump_jsonl(Path(args.output_blind), blind_rows)
    dump_json(Path(args.output_manifest), manifest)
    print(json.dumps({"output_batch": args.output_batch, "output_blind": args.output_blind, **manifest}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
