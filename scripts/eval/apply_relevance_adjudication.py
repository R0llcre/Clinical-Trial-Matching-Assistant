#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

VALID_LABELS = {0, 1, 2}


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


def _validate_rows(rows: Sequence[Dict[str, Any]], *, source: str) -> None:
    seen: set[Tuple[str, str]] = set()
    for idx, row in enumerate(rows, start=1):
        query_id, nct_id = _pair_key(row)
        if not query_id or not nct_id:
            raise ValueError(f"{source}[{idx}] missing query_id or nct_id")
        key = (query_id, nct_id)
        if key in seen:
            raise ValueError(f"{source}[{idx}] duplicate pair: {key}")
        seen.add(key)

        label = row.get("relevance_label")
        if isinstance(label, bool) or not isinstance(label, int) or label not in VALID_LABELS:
            raise ValueError(f"{source}[{idx}] invalid relevance_label: {label}")


def apply_adjudication(
    *,
    base_rows: Sequence[Dict[str, Any]],
    adjudication_rows: Sequence[Dict[str, Any]],
    output_annotator_id: str = "adjudicated",
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    _validate_rows(base_rows, source="base")
    _validate_rows(adjudication_rows, source="adjudication")

    adjudication_by_pair = {_pair_key(row): row for row in adjudication_rows}
    base_by_pair = {_pair_key(row): row for row in base_rows}

    missing = sorted(pair for pair in adjudication_by_pair if pair not in base_by_pair)
    if missing:
        raise ValueError(
            "adjudication contains pairs absent in base labels: "
            f"count={len(missing)} first={missing[0]}"
        )

    transitions: Counter[Tuple[int, int]] = Counter()
    adjudicated_by_query: Dict[str, int] = defaultdict(int)
    final_rows: List[Dict[str, Any]] = []
    changed = 0

    for row in base_rows:
        key = _pair_key(row)
        out_row = dict(row)
        override = adjudication_by_pair.get(key)
        if override is None:
            final_rows.append(out_row)
            continue

        old_label = int(out_row["relevance_label"])
        new_label = int(override["relevance_label"])
        transitions[(old_label, new_label)] += 1
        adjudicated_by_query[key[0]] += 1

        if old_label != new_label:
            changed += 1

        out_row["relevance_label"] = new_label
        if "rationale" in override:
            out_row["rationale"] = str(override.get("rationale") or "").strip()
        out_row["annotator_id"] = output_annotator_id
        if "guideline_version" in override:
            out_row["guideline_version"] = str(override.get("guideline_version") or "").strip()
        out_row["adjudicated"] = True

        final_rows.append(out_row)

    final_dist = Counter(int(row["relevance_label"]) for row in final_rows)
    manifest = {
        "base_rows": len(base_rows),
        "adjudication_rows": len(adjudication_rows),
        "adjudicated_pairs_applied": len(adjudication_rows),
        "changed_pairs": changed,
        "changed_rate": round((changed / len(adjudication_rows)), 4) if adjudication_rows else 0.0,
        "label_transitions": {f"{a}->{b}": count for (a, b), count in sorted(transitions.items())},
        "final_label_distribution": {
            str(label): final_dist.get(label, 0) for label in sorted(VALID_LABELS)
        },
        "adjudicated_by_query": dict(sorted(adjudicated_by_query.items())),
        "output_annotator_id": output_annotator_id,
    }
    return final_rows, manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply adjudication labels onto a base relevance label file."
    )
    parser.add_argument(
        "--base",
        default="eval/archive/m4_history/annotations/relevance.v2.round1.annotator_b.jsonl",
        help="Base label file (typically annotator_b full round)",
    )
    parser.add_argument(
        "--adjudication",
        default="eval/archive/m4_history/annotations/relevance.v2.round1.adjudication.annotator_a.jsonl",
        help="Adjudication label file (subset with final labels)",
    )
    parser.add_argument(
        "--output-jsonl",
        default="eval/annotations/relevance.v2.round1.final.jsonl",
    )
    parser.add_argument(
        "--output-manifest",
        default="eval/annotations/manifest.relevance.v2.round1.final.json",
    )
    parser.add_argument(
        "--output-annotator-id",
        default="adjudicated",
        help="annotator_id value written for adjudicated rows",
    )
    args = parser.parse_args()

    base_rows = load_jsonl(Path(args.base))
    adjudication_rows = load_jsonl(Path(args.adjudication))
    final_rows, manifest = apply_adjudication(
        base_rows=base_rows,
        adjudication_rows=adjudication_rows,
        output_annotator_id=args.output_annotator_id,
    )

    dump_jsonl(Path(args.output_jsonl), final_rows)
    dump_json(Path(args.output_manifest), manifest)
    print(json.dumps({"output": args.output_jsonl, **manifest}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
