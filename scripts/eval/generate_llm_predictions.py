#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List


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


def append_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def load_existing_predictions(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    existing: Dict[str, Dict[str, Any]] = {}
    for row in load_jsonl(path):
        nct_id = str(row.get("nct_id") or "").strip()
        if nct_id:
            existing[nct_id] = row
    return existing


def _import_llm_parser():
    repo_root = Path(__file__).resolve().parents[2]
    worker_root = repo_root / "apps" / "worker"
    if str(worker_root) not in sys.path:
        sys.path.insert(0, str(worker_root))
    from services.llm_eligibility_parser import parse_criteria_llm_v1_with_fallback

    return parse_criteria_llm_v1_with_fallback


def _safe_int(value: Any) -> int:
    return value if isinstance(value, int) else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate predicted parsing rules using llm_v1 with fallback."
    )
    parser.add_argument("--trials", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="")
    parser.add_argument("--limit", type=int, default=0, help="0 means all trials")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip nct_ids already present in output file.",
    )
    args = parser.parse_args()

    if args.model.strip():
        os.environ["OPENAI_MODEL"] = args.model.strip()

    parse_criteria_llm_v1_with_fallback = _import_llm_parser()

    trials = load_jsonl(Path(args.trials))
    if args.limit > 0:
        trials = trials[: args.limit]

    output_path = Path(args.output)
    existing = load_existing_predictions(output_path) if args.resume else {}
    skip_ids = set(existing.keys())

    stats: Dict[str, Any] = {
        "trial_count": len(trials),
        "already_present": len(skip_ids),
        "processed": 0,
        "written": 0,
        "source_llm_v1": 0,
        "source_rule_v1": 0,
        "fallback_count": 0,
        "error_count": 0,
        "rule_count": 0,
        "token_usage_total": 0,
        "elapsed_sec": 0.0,
    }

    start = time.time()
    for idx, row in enumerate(trials, start=1):
        nct_id = str(row.get("nct_id") or "").strip()
        if not nct_id:
            continue
        if nct_id in skip_ids:
            continue

        text = str(row.get("eligibility_text") or "")
        error_message = None
        try:
            rules, metadata = parse_criteria_llm_v1_with_fallback(text)
        except Exception as exc:  # pragma: no cover - defensive path for live runs
            rules = []
            metadata = {
                "parser_source": "error",
                "fallback_used": True,
                "fallback_reason": str(exc),
                "llm_usage": None,
            }
            error_message = str(exc)

        source = str(metadata.get("parser_source") or "")
        if source == "llm_v1":
            stats["source_llm_v1"] += 1
        elif source == "rule_v1":
            stats["source_rule_v1"] += 1
        if metadata.get("fallback_used"):
            stats["fallback_count"] += 1
        if error_message:
            stats["error_count"] += 1

        usage = metadata.get("llm_usage") or {}
        stats["token_usage_total"] += _safe_int(usage.get("total_tokens"))
        stats["rule_count"] += len(rules)
        stats["processed"] += 1

        append_jsonl(
            output_path,
            [
                {
                    "nct_id": nct_id,
                    "predicted_rules": rules,
                    "parser_metadata": metadata,
                }
            ],
        )
        stats["written"] += 1

        print(
            f"[{idx}/{len(trials)}] nct_id={nct_id} "
            f"source={source or 'unknown'} fallback={bool(metadata.get('fallback_used'))} "
            f"rules={len(rules)}",
            flush=True,
        )

    stats["elapsed_sec"] = round(time.time() - start, 2)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
