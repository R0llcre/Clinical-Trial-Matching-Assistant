#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional, Sequence

from run_evaluation import (
    _load_gold_rules,
    compute_hallucination_rate,
    compute_parse_metrics,
    generate_predicted_rules,
    load_jsonl,
)


def _collect_rule_stats(trials: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    field_counter: Counter[str] = Counter()
    per_trial_rule_counts: List[int] = []
    total_rules = 0

    for trial in trials:
        rules = trial.get("labeled_rules")
        if not isinstance(rules, list):
            rules = []
        valid_rules = [rule for rule in rules if isinstance(rule, dict)]
        per_trial_rule_counts.append(len(valid_rules))
        total_rules += len(valid_rules)
        for rule in valid_rules:
            field = str(rule.get("field") or "").strip().lower() or "unknown"
            field_counter[field] += 1

    if per_trial_rule_counts:
        min_rules = min(per_trial_rule_counts)
        max_rules = max(per_trial_rule_counts)
        median_rules = float(median(per_trial_rule_counts))
    else:
        min_rules = 0
        max_rules = 0
        median_rules = 0.0

    return {
        "gold_rule_count": total_rules,
        "unique_fields": len(field_counter),
        "field_distribution": dict(sorted(field_counter.items())),
        "rules_per_trial": {
            "min": min_rules,
            "median": round(median_rules, 4),
            "max": max_rules,
        },
    }


def build_report(
    *,
    trials: Sequence[Dict[str, Any]],
    predicted_rules_by_trial: Dict[str, List[Dict[str, Any]]],
    runtime: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    gold_rules = _load_gold_rules(trials)
    parse_metrics = compute_parse_metrics(gold_rules, predicted_rules_by_trial)
    hallucination_metrics = compute_hallucination_rate(trials, predicted_rules_by_trial)
    rule_stats = _collect_rule_stats(trials)

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "trial_count": len(trials),
            **rule_stats,
        },
        "metrics": {
            "parsing": parse_metrics,
            "hallucination": hallucination_metrics,
        },
    }
    if runtime:
        report["runtime"] = runtime
    return report


def render_markdown(report: Dict[str, Any]) -> str:
    dataset = report["dataset"]
    parsing = report["metrics"]["parsing"]
    hallucination = report["metrics"]["hallucination"]

    lines: List[str] = []
    lines.append("# Parsing Release Report")
    lines.append("")
    lines.append(f"- generated_at_utc: {report['generated_at_utc']}")
    lines.append(f"- trial_count: {dataset['trial_count']}")
    lines.append(f"- gold_rule_count: {dataset['gold_rule_count']}")
    lines.append(f"- unique_fields: {dataset['unique_fields']}")
    runtime = report.get("runtime") or {}
    prediction_source = runtime.get("prediction_source")
    if prediction_source:
        lines.append(f"- prediction_source: {prediction_source}")
    if runtime.get("curated_override_forced_off") is True:
        lines.append("- curated_overrides_forced_off: true")
    lines.append(
        "- rules_per_trial(min/median/max): "
        f"{dataset['rules_per_trial']['min']}/"
        f"{dataset['rules_per_trial']['median']}/"
        f"{dataset['rules_per_trial']['max']}"
    )
    lines.append("")
    lines.append("## Metric Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | ---: |")
    lines.append(f"| Parsing Precision | {parsing['precision']} |")
    lines.append(f"| Parsing Recall | {parsing['recall']} |")
    lines.append(f"| Parsing F1 | {parsing['f1']} |")
    lines.append(f"| Hallucination Rate | {hallucination['hallucination_rate']} |")
    lines.append("")
    lines.append("## Field Distribution")
    lines.append("")
    lines.append("| Field | Count |")
    lines.append("| --- | ---: |")
    field_distribution = dataset.get("field_distribution") or {}
    if field_distribution:
        for field, count in field_distribution.items():
            lines.append(f"| {field} | {count} |")
    else:
        lines.append("| none | 0 |")
    return "\n".join(lines) + "\n"


def dump_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate parsing release report from labeled trials."
    )
    parser.add_argument("--trials", default="eval/data/trials_parsing_release.jsonl")
    parser.add_argument(
        "--predicted-rules",
        default="",
        help="Optional JSONL with fields nct_id/predicted_rules; empty means parse_criteria_v1.",
    )
    parser.add_argument(
        "--respect-curated-overrides",
        action="store_true",
        help=(
            "When using in-process parser (without --predicted-rules), "
            "keep CTMA_ENABLE_CURATED_PARSER_OVERRIDES as-is."
        ),
    )
    parser.add_argument("--output-md", default="eval/reports/parsing_release_report.md")
    parser.add_argument("--output-json", default="eval/reports/parsing_release_report.json")
    args = parser.parse_args()

    trials = load_jsonl(Path(args.trials))
    forced_off = False
    previous_override_env = os.environ.get("CTMA_ENABLE_CURATED_PARSER_OVERRIDES")
    if not args.predicted_rules and not args.respect_curated_overrides:
        os.environ["CTMA_ENABLE_CURATED_PARSER_OVERRIDES"] = "0"
        forced_off = True
    try:
        predicted_rules_by_trial = generate_predicted_rules(trials, args.predicted_rules)
    finally:
        if previous_override_env is None:
            os.environ.pop("CTMA_ENABLE_CURATED_PARSER_OVERRIDES", None)
        else:
            os.environ["CTMA_ENABLE_CURATED_PARSER_OVERRIDES"] = previous_override_env

    prediction_source = (
        "predicted_rules_file" if args.predicted_rules else "rule_v1"
    )
    report = build_report(
        trials=trials,
        predicted_rules_by_trial=predicted_rules_by_trial,
        runtime={
            "prediction_source": prediction_source,
            "predicted_rules_path": args.predicted_rules or None,
            "curated_override_forced_off": forced_off,
        },
    )

    output_md = Path(args.output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown(report), encoding="utf-8")

    dump_json(Path(args.output_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
