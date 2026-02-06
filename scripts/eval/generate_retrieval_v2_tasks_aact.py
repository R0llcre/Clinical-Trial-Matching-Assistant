#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from generate_retrieval_v2_tasks import (
    DEFAULT_EXCLUDE_FILES,
    QUERY_SYNONYMS,
    build_round_batch,
    build_pending_rows,
    dump_json,
    dump_jsonl,
    load_excluded_pairs,
    load_jsonl,
)


def _norm_text(text: str) -> str:
    return " ".join((text or "").lower().replace("-", " ").split())


def _tokenize(text: str) -> set[str]:
    return {token for token in _norm_text(text).split() if len(token) > 2}


def _iter_aact_rows(zip_path: Path, member_name: str) -> Iterable[Dict[str, str]]:
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open(member_name) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
            reader = csv.reader(text, delimiter="|")
            header = next(reader, None)
            if header is None:
                return
            keys = [str(item).strip() for item in header]
            for row in reader:
                if not row:
                    continue
                payload = {keys[idx]: row[idx] if idx < len(row) else "" for idx in range(len(keys))}
                yield payload


def _query_condition_specs(query: Dict[str, Any]) -> Dict[str, Any]:
    expected_conditions = [
        item.strip()
        for item in (query.get("expected_conditions") or [])
        if isinstance(item, str) and item.strip()
    ]
    phrases: List[str] = []
    for condition in expected_conditions:
        phrases.append(_norm_text(condition))
        phrases.extend(_norm_text(item) for item in QUERY_SYNONYMS.get(_norm_text(condition), []))
    deduped_phrases = [phrase for phrase in dict.fromkeys(phrases) if phrase]
    tokens = set()
    for phrase in deduped_phrases:
        tokens |= _tokenize(phrase)
    return {
        "phrases": deduped_phrases,
        "tokens": tokens,
    }


def _condition_match(condition_name: str, spec: Dict[str, Any]) -> List[str]:
    text = _norm_text(condition_name)
    if not text:
        return []

    hits: List[str] = []
    for phrase in spec["phrases"]:
        if phrase and phrase in text:
            hits.append(phrase)
    if hits:
        return hits

    overlap = _tokenize(text) & set(spec["tokens"])
    if len(overlap) >= 2:
        return sorted(overlap)
    return []


def build_candidates_from_aact_zip(
    *,
    zip_path: Path,
    queries: Sequence[Dict[str, Any]],
    max_candidates_per_query: int,
    background_per_query: int,
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    query_specs: Dict[str, Dict[str, Any]] = {}
    query_maps: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for query in queries:
        query_id = str(query.get("query_id") or "").strip()
        if not query_id:
            continue
        query_specs[query_id] = _query_condition_specs(query)
        query_maps[query_id] = {}

    # Pass 1: from conditions table, collect likely-positive nct_ids for each query.
    for row in _iter_aact_rows(zip_path, "conditions.txt"):
        nct_id = str(row.get("nct_id") or "").strip()
        condition_name = str(row.get("name") or "").strip()
        if not nct_id or not condition_name:
            continue
        for query_id, spec in query_specs.items():
            hits = _condition_match(condition_name, spec)
            if not hits:
                continue
            bucket = query_maps[query_id].setdefault(
                nct_id,
                {
                    "nct_id": nct_id,
                    "conditions": set(),
                    "term_hits": set(),
                    "match_count": 0,
                },
            )
            bucket["conditions"].add(condition_name)
            bucket["term_hits"].update(hits)
            bucket["match_count"] = int(bucket["match_count"]) + 1

    # Select top positives per query, reserve space for background negatives.
    positive_cap = max(max_candidates_per_query - background_per_query, 1)
    selected_positive: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for query_id, candidate_map in query_maps.items():
        ranked = sorted(
            candidate_map.values(),
            key=lambda item: (
                -int(item["match_count"]),
                -len(item["term_hits"]),
                str(item["nct_id"]),
            ),
        )
        trimmed = ranked[:positive_cap]
        selected_positive[query_id] = {item["nct_id"]: item for item in trimmed}

    global_positive_ncts = sorted(
        {
            nct_id
            for per_query in selected_positive.values()
            for nct_id in per_query
        }
    )
    if not global_positive_ncts:
        raise RuntimeError(
            "AACT matching produced zero candidates; adjust query terms or data source."
        )

    # Build helper map of nct -> representative conditions observed in pass 1.
    nct_conditions: Dict[str, List[str]] = defaultdict(list)
    for per_query in selected_positive.values():
        for nct_id, payload in per_query.items():
            for name in sorted(payload["conditions"]):
                if len(nct_conditions[nct_id]) >= 8:
                    break
                if name not in nct_conditions[nct_id]:
                    nct_conditions[nct_id].append(name)

    # Pass 2: studies metadata for selected nct_ids.
    studies_map: Dict[str, Dict[str, Any]] = {}
    selected_nct_set = set(global_positive_ncts)
    for row in _iter_aact_rows(zip_path, "studies.txt"):
        nct_id = str(row.get("nct_id") or "").strip()
        if nct_id not in selected_nct_set:
            continue
        phase_raw = str(row.get("phase") or "").strip()
        phases = [part.strip() for part in phase_raw.split("|") if part.strip()] if phase_raw else []
        if phase_raw and not phases:
            phases = [phase_raw]
        studies_map[nct_id] = {
            "nct_id": nct_id,
            "title": str(row.get("brief_title") or "").strip(),
            "conditions": nct_conditions.get(nct_id, []),
            "status": str(row.get("overall_status") or "").strip(),
            "phases": phases,
            "locations": [],
            "term_hits": [],
        }

    # Pass 3: facilities metadata for location matching.
    for row in _iter_aact_rows(zip_path, "facilities.txt"):
        nct_id = str(row.get("nct_id") or "").strip()
        if nct_id not in studies_map:
            continue
        location = {
            "country": str(row.get("country") or "").strip(),
            "state": str(row.get("state") or "").strip(),
            "city": str(row.get("city") or "").strip(),
        }
        if not any(location.values()):
            continue
        locations = studies_map[nct_id]["locations"]
        if len(locations) < 8:
            locations.append(location)

    # Build final candidates per query: positives + cross-query background negatives.
    candidates_by_query: Dict[str, List[Dict[str, Any]]] = {}
    summary: Dict[str, Any] = {"queries": {}, "global_positive_ncts": len(global_positive_ncts)}
    for query_id in sorted(selected_positive):
        positives = selected_positive[query_id]
        rows: List[Dict[str, Any]] = []
        for nct_id, payload in positives.items():
            study = studies_map.get(nct_id)
            if not study:
                continue
            entry = dict(study)
            entry["term_hits"] = sorted(payload["term_hits"])
            rows.append(entry)

        # Add background candidates sampled from positives of other queries.
        background_needed = max(max_candidates_per_query - len(rows), 0)
        if background_needed > 0:
            for nct_id in global_positive_ncts:
                if nct_id in positives:
                    continue
                study = studies_map.get(nct_id)
                if not study:
                    continue
                rows.append(dict(study))
                if len(rows) >= max_candidates_per_query:
                    break

        rows = rows[:max_candidates_per_query]
        candidates_by_query[query_id] = rows
        summary["queries"][query_id] = {
            "positive_candidates": len(positives),
            "final_candidates": len(rows),
        }

    return candidates_by_query, summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build v2 retrieval pool from AACT flatfile snapshot and generate round-1 batch."
    )
    parser.add_argument(
        "--aact-zip",
        default="/tmp/aact/aact_flatfiles_latest.zip",
        help="Path to AACT flatfile zip snapshot",
    )
    parser.add_argument("--queries", default="eval/data/queries.jsonl")
    parser.add_argument("--max-candidates-per-query", type=int, default=220)
    parser.add_argument("--background-per-query", type=int, default=40)
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Additional JSONL files containing query_id/nct_id pairs to exclude",
    )
    parser.add_argument(
        "--output-pending",
        default="eval/annotation_tasks/relevance.pending.v2.jsonl",
    )
    parser.add_argument(
        "--output-batch",
        default="eval/annotation_tasks/relevance.batch_v2_round1.700.jsonl",
    )
    parser.add_argument(
        "--output-manifest",
        default="eval/annotation_tasks/manifest.relevance_v2_round1.json",
    )
    parser.add_argument("--target-per-query", type=int, default=70)
    parser.add_argument("--likely2-quota", type=int, default=20)
    parser.add_argument("--likely1-quota", type=int, default=30)
    parser.add_argument("--hard-negative-quota", type=int, default=20)
    parser.add_argument("--task-id-prefix", default="relevance-v2r1")
    args = parser.parse_args()

    aact_zip = Path(args.aact_zip)
    if not aact_zip.exists():
        raise FileNotFoundError(f"AACT zip not found: {aact_zip}")

    queries = load_jsonl(Path(args.queries))
    exclude_paths: List[Path] = []
    for default_path in DEFAULT_EXCLUDE_FILES:
        path = Path(default_path)
        if path.exists():
            exclude_paths.append(path)
    for item in args.exclude:
        path = Path(item)
        if path not in exclude_paths:
            exclude_paths.append(path)
    excluded_pairs = load_excluded_pairs(exclude_paths)

    candidates_by_query, source_summary = build_candidates_from_aact_zip(
        zip_path=aact_zip,
        queries=queries,
        max_candidates_per_query=args.max_candidates_per_query,
        background_per_query=args.background_per_query,
    )

    pending_rows, pending_summary = build_pending_rows(
        queries=queries,
        candidates_by_query=candidates_by_query,
        excluded_pairs=excluded_pairs,
        max_candidates_per_query=args.max_candidates_per_query,
    )
    batch_rows, batch_summary = build_round_batch(
        pending_rows,
        target_per_query=args.target_per_query,
        likely2_quota=args.likely2_quota,
        likely1_quota=args.likely1_quota,
        hard_negative_quota=args.hard_negative_quota,
        task_id_prefix=args.task_id_prefix,
    )

    output_pending = Path(args.output_pending)
    output_batch = Path(args.output_batch)
    output_manifest = Path(args.output_manifest)
    dump_jsonl(output_pending, pending_rows)
    dump_jsonl(output_batch, batch_rows)

    manifest = {
        "source": {
            "type": "aact_flatfile",
            "zip_path": str(aact_zip),
            "summary": source_summary,
        },
        "queries_path": args.queries,
        "excluded_files": [str(path) for path in exclude_paths],
        "excluded_pair_count": len(excluded_pairs),
        "pending": {
            "path": str(output_pending),
            "total_rows": len(pending_rows),
            "query_summary": pending_summary["queries"],
        },
        "batch_round_1": {
            "path": str(output_batch),
            "total_rows": len(batch_rows),
            "target_per_query": args.target_per_query,
            "quotas": {
                "likely_2": args.likely2_quota,
                "likely_1": args.likely1_quota,
                "hard_negative": args.hard_negative_quota,
            },
            "task_id_prefix": args.task_id_prefix,
            "query_summary": batch_summary["queries"],
        },
    }
    dump_json(output_manifest, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
