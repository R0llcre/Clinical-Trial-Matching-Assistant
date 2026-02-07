#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from compute_parsing_agreement import rule_signature


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


def _nct_key(row: Dict[str, Any]) -> str:
    return str(row.get("nct_id") or "").strip()


def _validate_rows(rows: Sequence[Dict[str, Any]], *, source: str) -> None:
    seen: set[str] = set()
    for idx, row in enumerate(rows, start=1):
        nct_id = _nct_key(row)
        if not nct_id:
            raise ValueError(f"{source}[{idx}] missing nct_id")
        if nct_id in seen:
            raise ValueError(f"{source}[{idx}] duplicate nct_id: {nct_id}")
        seen.add(nct_id)
        labeled_rules = row.get("labeled_rules")
        if not isinstance(labeled_rules, list):
            raise ValueError(f"{source}[{idx}] labeled_rules must be list")


def _rule_set(row: Dict[str, Any]) -> set[Tuple[str, str, str, str, str]]:
    signatures: set[Tuple[str, str, str, str, str]] = set()
    for rule in row.get("labeled_rules", []):
        if not isinstance(rule, dict):
            continue
        signatures.add(rule_signature(rule))
    return signatures


def apply_parsing_adjudication(
    *,
    base_rows: Sequence[Dict[str, Any]],
    adjudicated_rows: Sequence[Dict[str, Any]],
    output_annotator_id: str = "adjudicated",
    strict_missing_in_base: bool = False,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    _validate_rows(base_rows, source="base")
    _validate_rows(adjudicated_rows, source="adjudicated")

    base_by_nct = {_nct_key(row): row for row in base_rows}
    adjudicated_by_nct = {_nct_key(row): row for row in adjudicated_rows}

    missing_in_base = sorted(nct_id for nct_id in adjudicated_by_nct if nct_id not in base_by_nct)
    if strict_missing_in_base and missing_in_base:
        raise ValueError(
            "adjudicated contains nct_id absent in base set: "
            f"count={len(missing_in_base)} first={missing_in_base[0]}"
        )

    overlaps = sorted(nct_id for nct_id in adjudicated_by_nct if nct_id in base_by_nct)
    changed_trials = 0
    final_rows: List[Dict[str, Any]] = []
    applied_by_guideline: Counter[str] = Counter()

    for row in base_rows:
        nct_id = _nct_key(row)
        out_row = dict(row)
        override = adjudicated_by_nct.get(nct_id)
        if override is None:
            final_rows.append(out_row)
            continue

        before = _rule_set(out_row)
        after_rules = [rule for rule in override.get("labeled_rules", []) if isinstance(rule, dict)]
        out_row["labeled_rules"] = after_rules
        out_row["annotator_id"] = output_annotator_id
        if "guideline_version" in override:
            out_row["guideline_version"] = str(override.get("guideline_version") or "").strip()
        out_row["adjudicated"] = True
        out_row["adjudication_source"] = "parsing_relabel_round1"

        after = _rule_set(out_row)
        if before != after:
            changed_trials += 1
        applied_by_guideline[str(out_row.get("guideline_version") or "").strip()] += 1
        final_rows.append(out_row)

    manifest = {
        "base_trials": len(base_rows),
        "adjudicated_trials": len(adjudicated_rows),
        "overlap_trials_applied": len(overlaps),
        "missing_in_base": len(missing_in_base),
        "changed_trials": changed_trials,
        "changed_rate": round((changed_trials / len(overlaps)), 4) if overlaps else 0.0,
        "output_annotator_id": output_annotator_id,
        "strict_missing_in_base": strict_missing_in_base,
        "applied_guideline_versions": dict(sorted(applied_by_guideline.items())),
    }
    return final_rows, manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply parsing adjudication rows onto a base parsing dataset by nct_id."
    )
    parser.add_argument("--base", required=True, help="Base parsing dataset JSONL.")
    parser.add_argument("--adjudicated", required=True, help="Adjudicated parsing JSONL.")
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--output-manifest", required=True)
    parser.add_argument("--output-annotator-id", default="annotator_c")
    parser.add_argument(
        "--strict-missing-in-base",
        action="store_true",
        help="Fail when adjudicated contains nct_id absent in base file.",
    )
    args = parser.parse_args()

    final_rows, manifest = apply_parsing_adjudication(
        base_rows=load_jsonl(Path(args.base)),
        adjudicated_rows=load_jsonl(Path(args.adjudicated)),
        output_annotator_id=args.output_annotator_id,
        strict_missing_in_base=args.strict_missing_in_base,
    )
    dump_jsonl(Path(args.output_jsonl), final_rows)
    dump_json(Path(args.output_manifest), manifest)
    print(json.dumps({"output": args.output_jsonl, **manifest}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
