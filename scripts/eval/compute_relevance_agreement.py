#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

VALID_LABELS = {0, 1, 2}


def load_labels(path: Path) -> Dict[Tuple[str, str], int]:
    labels: Dict[Tuple[str, str], int] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} invalid json: {exc}") from exc

            query_id = str(payload.get("query_id", "")).strip()
            nct_id = str(payload.get("nct_id", "")).strip()
            label = payload.get("relevance_label")
            if not query_id or not nct_id:
                raise ValueError(f"{path}:{line_no} missing query_id or nct_id")
            if isinstance(label, bool) or not isinstance(label, int) or label not in VALID_LABELS:
                raise ValueError(
                    f"{path}:{line_no} relevance_label must be one of {sorted(VALID_LABELS)}"
                )

            key = (query_id, nct_id)
            if key in labels:
                raise ValueError(f"{path}:{line_no} duplicate key {key}")
            labels[key] = label
    return labels


def compute_confusion(
    a_labels: Dict[Tuple[str, str], int], b_labels: Dict[Tuple[str, str], int]
) -> Dict[str, int]:
    matrix = {f"{i}->{j}": 0 for i in sorted(VALID_LABELS) for j in sorted(VALID_LABELS)}
    for key in sorted(a_labels):
        matrix[f"{a_labels[key]}->{b_labels[key]}"] += 1
    return matrix


def cohen_kappa(a: List[int], b: List[int]) -> float:
    total = len(a)
    if total == 0:
        return 0.0
    agree = sum(1 for x, y in zip(a, b) if x == y)
    p0 = agree / total

    a_count = Counter(a)
    b_count = Counter(b)
    pe = sum((a_count[label] / total) * (b_count[label] / total) for label in VALID_LABELS)
    if pe == 1:
        return 1.0
    return (p0 - pe) / (1 - pe)


def collect_mismatches(
    a_labels: Dict[Tuple[str, str], int], b_labels: Dict[Tuple[str, str], int]
) -> List[Dict[str, object]]:
    mismatches: List[Dict[str, object]] = []
    for query_id, nct_id in sorted(a_labels):
        a_label = a_labels[(query_id, nct_id)]
        b_label = b_labels[(query_id, nct_id)]
        if a_label != b_label:
            mismatches.append(
                {
                    "query_id": query_id,
                    "nct_id": nct_id,
                    "label_a": a_label,
                    "label_b": b_label,
                }
            )
    return mismatches


def dump_jsonl(path: Path, rows: Iterable[Dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute agreement metrics for relevance annotation JSONL files."
    )
    parser.add_argument("--a", required=True, help="Annotator A JSONL file path")
    parser.add_argument("--b", required=True, help="Annotator B JSONL file path")
    parser.add_argument(
        "--mismatches-out",
        default="",
        help="Optional path to write mismatches JSONL",
    )
    args = parser.parse_args()

    a_path = Path(args.a)
    b_path = Path(args.b)
    a_labels = load_labels(a_path)
    b_labels = load_labels(b_path)

    if set(a_labels.keys()) != set(b_labels.keys()):
        only_a = len(set(a_labels.keys()) - set(b_labels.keys()))
        only_b = len(set(b_labels.keys()) - set(a_labels.keys()))
        raise ValueError(
            "annotation keys mismatch between files: "
            f"only_in_a={only_a}, only_in_b={only_b}"
        )

    ordered_keys = sorted(a_labels.keys())
    a_ordered = [a_labels[key] for key in ordered_keys]
    b_ordered = [b_labels[key] for key in ordered_keys]

    total = len(ordered_keys)
    matches = sum(1 for x, y in zip(a_ordered, b_ordered) if x == y)
    percent_agreement = (matches / total) if total else 0.0
    kappa = cohen_kappa(a_ordered, b_ordered)
    confusion = compute_confusion(a_labels, b_labels)
    mismatches = collect_mismatches(a_labels, b_labels)

    if args.mismatches_out:
        dump_jsonl(Path(args.mismatches_out), mismatches)

    summary = {
        "total_pairs": total,
        "exact_matches": matches,
        "percent_agreement": round(percent_agreement, 4),
        "cohen_kappa": round(kappa, 4),
        "mismatch_count": len(mismatches),
        "confusion": confusion,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
