#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

from compute_relevance_agreement import (
    VALID_LABELS,
    cohen_kappa,
    compute_confusion,
    load_labels,
)


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


def _validate_rows(rows: Sequence[Dict[str, Any]], *, source: str) -> None:
    for idx, row in enumerate(rows, start=1):
        query_id = str(row.get("query_id") or "").strip()
        nct_id = str(row.get("nct_id") or "").strip()
        label = row.get("relevance_label")
        if not query_id or not nct_id:
            raise ValueError(f"{source}[{idx}] missing query_id or nct_id")
        if isinstance(label, bool) or not isinstance(label, int) or label not in VALID_LABELS:
            raise ValueError(f"{source}[{idx}] invalid relevance_label: {label}")


def _label_distribution(rows: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    counts = Counter(int(row["relevance_label"]) for row in rows)
    return {str(label): counts.get(label, 0) for label in sorted(VALID_LABELS)}


def _query_breakdown(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_query: Dict[str, List[int]] = defaultdict(list)
    for row in rows:
        by_query[str(row["query_id"])].append(int(row["relevance_label"]))

    breakdown: List[Dict[str, Any]] = []
    for query_id in sorted(by_query):
        labels = by_query[query_id]
        total = len(labels)
        rel = sum(1 for label in labels if label >= 1)
        strict = sum(1 for label in labels if label == 2)
        breakdown.append(
            {
                "query_id": query_id,
                "pair_count": total,
                "relevant_count_ge1": rel,
                "relevant_count_eq2": strict,
                "relevant_rate_ge1": round(rel / total, 4) if total else 0.0,
            }
        )
    return breakdown


def _overall_summary(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    query_ids = {str(row["query_id"]) for row in rows}
    nct_ids = {str(row["nct_id"]) for row in rows}
    total = len(rows)
    label_counts = _label_distribution(rows)
    rel_ge1 = int(label_counts["1"]) + int(label_counts["2"])
    rel_eq2 = int(label_counts["2"])
    return {
        "total_pairs": total,
        "query_count": len(query_ids),
        "nct_count": len(nct_ids),
        "avg_pairs_per_query": round((total / len(query_ids)), 4) if query_ids else 0.0,
        "label_distribution": label_counts,
        "relevant_rate_ge1": round((rel_ge1 / total), 4) if total else 0.0,
        "relevant_rate_eq2": round((rel_eq2 / total), 4) if total else 0.0,
    }


def _agreement_summary(
    a_path: Path, b_path: Path
) -> Dict[str, Any]:
    a_labels = load_labels(a_path)
    b_labels = load_labels(b_path)

    a_keys = set(a_labels)
    b_keys = set(b_labels)
    overlap = sorted(a_keys & b_keys)
    only_a = len(a_keys - b_keys)
    only_b = len(b_keys - a_keys)

    if not overlap:
        return {
            "overlap_pairs": 0,
            "only_in_a": only_a,
            "only_in_b": only_b,
            "exact_match_rate": 0.0,
            "cohen_kappa": 0.0,
            "confusion": {f"{i}->{j}": 0 for i in sorted(VALID_LABELS) for j in sorted(VALID_LABELS)},
        }

    a_vals = [a_labels[key] for key in overlap]
    b_vals = [b_labels[key] for key in overlap]
    exact = sum(1 for x, y in zip(a_vals, b_vals) if x == y)
    overlap_a = {key: a_labels[key] for key in overlap}
    overlap_b = {key: b_labels[key] for key in overlap}
    return {
        "overlap_pairs": len(overlap),
        "only_in_a": only_a,
        "only_in_b": only_b,
        "exact_match_rate": round(exact / len(overlap), 4),
        "cohen_kappa": round(cohen_kappa(a_vals, b_vals), 4),
        "confusion": compute_confusion(overlap_a, overlap_b),
    }


def build_report(
    *,
    annotator_a_path: Path,
    annotator_b_path: Path | None = None,
) -> Dict[str, Any]:
    rows_a = _load_rows(annotator_a_path)
    _validate_rows(rows_a, source="annotator_a")

    report: Dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": _overall_summary(rows_a),
        "query_breakdown": _query_breakdown(rows_a),
        "agreement": None,
    }
    if annotator_b_path is not None:
        report["agreement"] = _agreement_summary(annotator_a_path, annotator_b_path)
    return report


def render_markdown(report: Dict[str, Any]) -> str:
    dataset = report["dataset"]
    lines: List[str] = [
        "# Retrieval Annotation Report",
        "",
        f"- generated_at_utc: {report['generated_at_utc']}",
        f"- total_pairs: {dataset['total_pairs']}",
        f"- query_count: {dataset['query_count']}",
        f"- nct_count: {dataset['nct_count']}",
        f"- avg_pairs_per_query: {dataset['avg_pairs_per_query']}",
        f"- relevant_rate_ge1: {dataset['relevant_rate_ge1']}",
        f"- relevant_rate_eq2: {dataset['relevant_rate_eq2']}",
        "",
        "## Label Distribution",
        "",
        "| Label | Count |",
        "| --- | ---: |",
    ]

    for label in ("0", "1", "2"):
        lines.append(f"| {label} | {dataset['label_distribution'][label]} |")

    lines.extend(
        [
            "",
            "## Query Breakdown",
            "",
            "| Query | Pairs | Relevant(>=1) | Relevant(=2) | Relevant Rate(>=1) |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in report["query_breakdown"]:
        lines.append(
            "| {query_id} | {pair_count} | {relevant_count_ge1} | "
            "{relevant_count_eq2} | {relevant_rate_ge1} |".format(**row)
        )

    agreement = report.get("agreement")
    if agreement:
        lines.extend(
            [
                "",
                "## Annotator Agreement",
                "",
                f"- overlap_pairs: {agreement['overlap_pairs']}",
                f"- only_in_a: {agreement['only_in_a']}",
                f"- only_in_b: {agreement['only_in_b']}",
                f"- exact_match_rate: {agreement['exact_match_rate']}",
                f"- cohen_kappa: {agreement['cohen_kappa']}",
                "",
                "### Confusion (A -> B)",
                "",
                "| Pair | Count |",
                "| --- | ---: |",
            ]
        )
        for key, value in sorted(agreement["confusion"].items()):
            lines.append(f"| {key} | {value} |")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate retrieval-only annotation report.")
    parser.add_argument("--annotator-a", default="eval/annotations/relevance.annotator_a.jsonl")
    parser.add_argument("--annotator-b", default="eval/annotations/relevance.annotator_b.jsonl")
    parser.add_argument(
        "--output-md",
        default="eval/reports/retrieval_annotation_report_300.md",
    )
    parser.add_argument(
        "--output-json",
        default="eval/reports/retrieval_annotation_report_300.json",
    )
    args = parser.parse_args()

    annotator_a_path = Path(args.annotator_a)
    annotator_b_path = Path(args.annotator_b) if args.annotator_b else None

    report = build_report(
        annotator_a_path=annotator_a_path,
        annotator_b_path=annotator_b_path,
    )
    markdown = render_markdown(report)

    output_md = Path(args.output_md)
    output_json = Path(args.output_json)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(markdown, encoding="utf-8")
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main()
