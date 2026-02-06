#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple


def _load_rows(path: Path) -> List[Dict[str, Any]]:
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


def _validate_relevance_rows(rows: Sequence[Dict[str, Any]]) -> None:
    for idx, row in enumerate(rows, start=1):
        query_id = str(row.get("query_id") or "").strip()
        nct_id = str(row.get("nct_id") or "").strip()
        label = row.get("relevance_label")
        if not query_id or not nct_id:
            raise ValueError(f"rows[{idx}] missing query_id or nct_id")
        if isinstance(label, bool) or not isinstance(label, int) or label not in {0, 1, 2}:
            raise ValueError(f"rows[{idx}] invalid relevance_label: {label}")


def _dump_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def generate_retrieval_tasks(
    rows: Sequence[Dict[str, Any]],
    *,
    target_pairs: int,
    guideline_version: str = "m4-v1",
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    annotated_pairs = {
        (str(row["query_id"]).strip(), str(row["nct_id"]).strip())
        for row in rows
    }
    query_ids = sorted({query_id for query_id, _ in annotated_pairs})
    nct_ids = sorted({nct_id for _, nct_id in annotated_pairs})

    candidate_pairs: List[Tuple[str, str]] = []
    for query_id in query_ids:
        for nct_id in nct_ids:
            pair = (query_id, nct_id)
            if pair in annotated_pairs:
                continue
            candidate_pairs.append(pair)

    selected_pairs = candidate_pairs[:target_pairs]
    tasks = [
        {
            "task_id": f"relevance-{idx + 1:05d}",
            "query_id": query_id,
            "nct_id": nct_id,
            "status": "PENDING",
            "task_type": "relevance",
            "guideline_version": guideline_version,
        }
        for idx, (query_id, nct_id) in enumerate(selected_pairs)
    ]

    manifest = {
        "query_count": len(query_ids),
        "nct_count": len(nct_ids),
        "annotated_pairs": len(annotated_pairs),
        "cross_product_pairs": len(query_ids) * len(nct_ids),
        "candidate_unlabeled_pairs": len(candidate_pairs),
        "generated_tasks": len(tasks),
        "requested_tasks": target_pairs,
    }
    return tasks, manifest


def generate_parsing_tasks(
    rows: Sequence[Dict[str, Any]],
    *,
    target_trials: int,
    guideline_version: str = "m4-v1",
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    nct_counts = Counter(str(row["nct_id"]).strip() for row in rows)
    ranked_nct_ids = sorted(nct_counts.items(), key=lambda item: (-item[1], item[0]))
    selected = ranked_nct_ids[:target_trials]

    tasks = [
        {
            "task_id": f"parsing-{idx + 1:05d}",
            "nct_id": nct_id,
            "query_support_count": support_count,
            "status": "PENDING",
            "task_type": "rule_annotation",
            "guideline_version": guideline_version,
            "notes": "Fetch trial detail and annotate labeled_rules from eligibility text.",
        }
        for idx, (nct_id, support_count) in enumerate(selected)
    ]
    manifest = {
        "candidate_trials": len(ranked_nct_ids),
        "generated_tasks": len(tasks),
        "requested_tasks": target_trials,
    }
    return tasks, manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate large-scale annotation task lists for retrieval and parsing."
    )
    parser.add_argument("--source", default="eval/annotations/relevance.annotator_a.jsonl")
    parser.add_argument("--target-retrieval-pairs", type=int, default=2000)
    parser.add_argument("--target-parsing-trials", type=int, default=200)
    parser.add_argument(
        "--output-retrieval",
        default="eval/annotation_tasks/relevance.pending.2000.jsonl",
    )
    parser.add_argument(
        "--output-parsing",
        default="eval/annotation_tasks/parsing.pending.200.jsonl",
    )
    parser.add_argument(
        "--output-manifest",
        default="eval/annotation_tasks/manifest.large_scale.json",
    )
    args = parser.parse_args()

    if args.target_retrieval_pairs < 1:
        raise ValueError("--target-retrieval-pairs must be >= 1")
    if args.target_parsing_trials < 1:
        raise ValueError("--target-parsing-trials must be >= 1")

    rows = _load_rows(Path(args.source))
    _validate_relevance_rows(rows)

    retrieval_tasks, retrieval_manifest = generate_retrieval_tasks(
        rows,
        target_pairs=args.target_retrieval_pairs,
    )
    parsing_tasks, parsing_manifest = generate_parsing_tasks(
        rows,
        target_trials=args.target_parsing_trials,
    )

    output_retrieval = Path(args.output_retrieval)
    output_parsing = Path(args.output_parsing)
    output_manifest = Path(args.output_manifest)

    _dump_jsonl(output_retrieval, retrieval_tasks)
    _dump_jsonl(output_parsing, parsing_tasks)
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    output_manifest.write_text(
        json.dumps(
            {
                "source": args.source,
                "retrieval": retrieval_manifest,
                "parsing": parsing_manifest,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "output_retrieval": str(output_retrieval),
                "output_parsing": str(output_parsing),
                "output_manifest": str(output_manifest),
                "retrieval": retrieval_manifest,
                "parsing": parsing_manifest,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
