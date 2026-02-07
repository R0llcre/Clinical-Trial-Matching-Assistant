#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from run_evaluation import (
    _load_gold_rules,
    compute_hallucination_rate,
    compute_parse_metrics,
    load_jsonl,
)


def _import_parsers():
    repo_root = Path(__file__).resolve().parents[2]
    worker_root = repo_root / "apps" / "worker"
    if str(worker_root) not in sys.path:
        sys.path.insert(0, str(worker_root))
    from services.eligibility_parser import parse_criteria_v1
    from services.llm_eligibility_parser import parse_criteria_llm_v1_with_fallback

    return parse_criteria_llm_v1_with_fallback, parse_criteria_v1


@dataclass(frozen=True)
class AblationConfig:
    name: str
    env: Dict[str, str]
    description: str


def default_configs() -> List[AblationConfig]:
    return [
        AblationConfig(
            name="strict_guarded",
            env={
                "OPENAI_PROMPT_STYLE": "strict_v1",
                "LLM_HALLUCINATION_THRESHOLD": "0.02",
                "LLM_CRITICAL_FIELDS": "age,sex,history",
                "LLM_MIN_RULE_COVERAGE_RATIO": "0.25",
                "LLM_MIN_FINAL_RULES": "1",
                "LLM_CONTRACT_POSTPROCESS_ENABLED": "1",
            },
            description="Current guarded baseline",
        ),
        AblationConfig(
            name="no_contract_postprocess",
            env={
                "OPENAI_PROMPT_STYLE": "strict_v1",
                "LLM_HALLUCINATION_THRESHOLD": "0.02",
                "LLM_CRITICAL_FIELDS": "age,sex,history",
                "LLM_MIN_RULE_COVERAGE_RATIO": "0.25",
                "LLM_MIN_FINAL_RULES": "1",
                "LLM_CONTRACT_POSTPROCESS_ENABLED": "0",
            },
            description="Disable contract-aligned rule postprocess",
        ),
        AblationConfig(
            name="no_hallucination_gate",
            env={
                "OPENAI_PROMPT_STYLE": "strict_v1",
                "LLM_HALLUCINATION_THRESHOLD": "1.0",
                "LLM_CRITICAL_FIELDS": "age,sex,history",
                "LLM_MIN_RULE_COVERAGE_RATIO": "0.25",
                "LLM_MIN_FINAL_RULES": "1",
                "LLM_CONTRACT_POSTPROCESS_ENABLED": "1",
            },
            description="Disable hallucination gate only",
        ),
        AblationConfig(
            name="no_critical_backfill",
            env={
                "OPENAI_PROMPT_STYLE": "strict_v1",
                "LLM_HALLUCINATION_THRESHOLD": "0.02",
                "LLM_CRITICAL_FIELDS": "",
                "LLM_MIN_RULE_COVERAGE_RATIO": "0.25",
                "LLM_MIN_FINAL_RULES": "1",
                "LLM_CONTRACT_POSTPROCESS_ENABLED": "1",
            },
            description="Disable age/sex/history backfill",
        ),
        AblationConfig(
            name="no_coverage_gate",
            env={
                "OPENAI_PROMPT_STYLE": "strict_v1",
                "LLM_HALLUCINATION_THRESHOLD": "0.02",
                "LLM_CRITICAL_FIELDS": "age,sex,history",
                "LLM_MIN_RULE_COVERAGE_RATIO": "0.0",
                "LLM_MIN_FINAL_RULES": "0",
                "LLM_CONTRACT_POSTPROCESS_ENABLED": "1",
            },
            description="Disable low-coverage quality gate",
        ),
        AblationConfig(
            name="precision_prompt",
            env={
                "OPENAI_PROMPT_STYLE": "precision_v1",
                "LLM_HALLUCINATION_THRESHOLD": "0.02",
                "LLM_CRITICAL_FIELDS": "age,sex,history",
                "LLM_MIN_RULE_COVERAGE_RATIO": "0.25",
                "LLM_MIN_FINAL_RULES": "1",
                "LLM_CONTRACT_POSTPROCESS_ENABLED": "1",
            },
            description="Prompt tuned toward higher precision",
        ),
        AblationConfig(
            name="recall_prompt",
            env={
                "OPENAI_PROMPT_STYLE": "recall_v1",
                "LLM_HALLUCINATION_THRESHOLD": "0.02",
                "LLM_CRITICAL_FIELDS": "age,sex,history",
                "LLM_MIN_RULE_COVERAGE_RATIO": "0.25",
                "LLM_MIN_FINAL_RULES": "1",
                "LLM_CONTRACT_POSTPROCESS_ENABLED": "1",
            },
            description="Prompt tuned toward higher recall",
        ),
    ]


@contextmanager
def patched_env(overrides: Dict[str, str]) -> Iterator[None]:
    previous: Dict[str, Optional[str]] = {}
    try:
        for key, value in overrides.items():
            previous[key] = os.environ.get(key)
            os.environ[key] = value
        yield
    finally:
        for key in overrides:
            old = previous.get(key)
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def evaluate_config(
    *,
    config: AblationConfig,
    model: str,
    trials: List[Dict[str, Any]],
) -> Dict[str, Any]:
    parse_criteria_llm_v1_with_fallback, parse_criteria_v1 = _import_parsers()

    predictions: Dict[str, List[Dict[str, Any]]] = {}
    source_counts = {"llm_v1": 0, "rule_v1": 0, "other": 0}
    fallback_count = 0
    error_count = 0
    token_prompt = 0
    token_completion = 0
    token_total = 0
    started_at = time.time()

    env = {
        "LLM_PARSER_ENABLED": "1",
        "OPENAI_MODEL": model,
        "OPENAI_TIMEOUT_SECONDS": "90",
        **config.env,
    }
    with patched_env(env):
        for trial in trials:
            nct_id = str(trial.get("nct_id") or "").strip()
            text = str(trial.get("eligibility_text") or "")
            if not nct_id:
                continue

            try:
                rules, metadata = parse_criteria_llm_v1_with_fallback(text)
            except Exception as exc:
                error_count += 1
                rules = parse_criteria_v1(text)
                metadata = {
                    "parser_source": "rule_v1",
                    "fallback_used": True,
                    "fallback_reason": str(exc),
                    "llm_usage": None,
                }

            predictions[nct_id] = rules
            source = str(metadata.get("parser_source") or "")
            if source in source_counts:
                source_counts[source] += 1
            else:
                source_counts["other"] += 1
            if metadata.get("fallback_used"):
                fallback_count += 1

            usage = metadata.get("llm_usage") or {}
            if isinstance(usage.get("prompt_tokens"), int):
                token_prompt += usage["prompt_tokens"]
            if isinstance(usage.get("completion_tokens"), int):
                token_completion += usage["completion_tokens"]
            if isinstance(usage.get("total_tokens"), int):
                token_total += usage["total_tokens"]

    gold_rules = _load_gold_rules(trials)
    parse_metrics = compute_parse_metrics(gold_rules, predictions)
    hallucination = compute_hallucination_rate(trials, predictions)

    return {
        "name": config.name,
        "description": config.description,
        "env": config.env,
        "elapsed_sec": round(time.time() - started_at, 2),
        "metrics": {
            "parsing": parse_metrics,
            "hallucination": hallucination,
        },
        "runtime": {
            "trial_count": len(trials),
            "source_counts": source_counts,
            "fallback_count": fallback_count,
            "fallback_rate": round(fallback_count / len(trials), 4) if trials else 0.0,
            "error_count": error_count,
            "token_usage": {
                "prompt_tokens": token_prompt,
                "completion_tokens": token_completion,
                "total_tokens": token_total,
            },
        },
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# LLM Ablation Report")
    lines.append("")
    lines.append(f"- generated_at_utc: {report['generated_at_utc']}")
    lines.append(f"- model: {report['model']}")
    lines.append(f"- trials: {report['trial_count']}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Config | F1 | Precision | Recall | Hallucination | Fallback Rate | Tokens |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")

    sorted_results = sorted(
        report["results"],
        key=lambda item: item["metrics"]["parsing"]["f1"],
        reverse=True,
    )
    for row in sorted_results:
        pm = row["metrics"]["parsing"]
        hm = row["metrics"]["hallucination"]
        rt = row["runtime"]
        lines.append(
            f"| {row['name']} | {pm['f1']} | {pm['precision']} | {pm['recall']} | "
            f"{hm['hallucination_rate']} | {rt['fallback_rate']} | {rt['token_usage']['total_tokens']} |"
        )

    lines.append("")
    lines.append("## Config Details")
    lines.append("")
    for row in sorted_results:
        lines.append(f"### {row['name']}")
        lines.append("")
        lines.append(f"- description: {row['description']}")
        lines.append(f"- elapsed_sec: {row['elapsed_sec']}")
        lines.append(f"- env: `{json.dumps(row['env'], ensure_ascii=False, sort_keys=True)}`")
        lines.append(f"- source_counts: `{json.dumps(row['runtime']['source_counts'], sort_keys=True)}`")
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run systematic LLM parsing ablation.")
    parser.add_argument("--trials", default="eval/data/trials_parsing_release.jsonl")
    parser.add_argument("--model", default="gpt-4.1")
    parser.add_argument("--limit", type=int, default=0, help="0 means all trials")
    parser.add_argument(
        "--output-json",
        default="eval/reports/llm_ablation_release.json",
    )
    parser.add_argument(
        "--output-md",
        default="eval/reports/llm_ablation_release.md",
    )
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for run_llm_ablation.py")

    trials = load_jsonl(Path(args.trials))
    if args.limit > 0:
        trials = trials[: args.limit]

    results: List[Dict[str, Any]] = []
    for config in default_configs():
        print(f"[ablation] running {config.name} ...", flush=True)
        result = evaluate_config(config=config, model=args.model, trials=trials)
        results.append(result)
        f1 = result["metrics"]["parsing"]["f1"]
        fallback_rate = result["runtime"]["fallback_rate"]
        print(
            f"[ablation] done {config.name}: f1={f1} fallback_rate={fallback_rate}",
            flush=True,
        )

    report = {
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": args.model,
        "trial_count": len(trials),
        "results": results,
    }

    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    output_md = Path(args.output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown(report), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
