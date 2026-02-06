#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from run_evaluation import (
    _load_gold_rules,
    _norm_text,
    build_heuristic_rankings,
    build_relevance_index,
    generate_predicted_rules,
    load_jsonl,
    load_retrieval_rankings,
    rule_signature,
    run_evaluation,
)

THRESHOLDS = {
    "top_k_hitrate": 0.70,
    "parsing_f1": 0.80,
    "hallucination_rate": 0.02,
}


def _retrieve_relevant_pairs(
    relevance_index: Dict[Tuple[str, str], int],
    query_id: str,
    threshold: int,
    allowed_nct_ids: set[str],
) -> List[Tuple[str, int]]:
    relevant: List[Tuple[str, int]] = []
    for (qid, nct_id), label in relevance_index.items():
        if qid == query_id and label >= threshold and nct_id in allowed_nct_ids:
            relevant.append((nct_id, label))
    relevant.sort(key=lambda item: (-item[1], item[0]))
    return relevant


def analyze_retrieval_errors(
    queries: List[Dict[str, Any]],
    rankings: Dict[str, List[str]],
    relevance_index: Dict[Tuple[str, str], int],
    *,
    top_k: int,
    relevance_threshold: int,
    sample_limit: int = 10,
) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
    error_counts: Counter[str] = Counter()
    samples: List[Dict[str, Any]] = []
    for query in queries:
        query_id = str(query.get("query_id") or "").strip()
        if not query_id:
            continue
        ranked_nct_ids = rankings.get(query_id, [])
        allowed_nct_ids = set(ranked_nct_ids)
        top_ids = ranked_nct_ids[:top_k]
        top_labels = [int(relevance_index.get((query_id, nct_id), 0)) for nct_id in top_ids]
        relevant_pairs = _retrieve_relevant_pairs(
            relevance_index, query_id, relevance_threshold, allowed_nct_ids
        )
        has_relevant = len(relevant_pairs) > 0
        hit_topk = any(label >= relevance_threshold for label in top_labels)
        top1_label = top_labels[0] if top_labels else 0

        if has_relevant and not hit_topk:
            error_counts["retrieval_miss_topk"] += 1
            if len(samples) < sample_limit:
                samples.append(
                    {
                        "error_type": "retrieval_miss_topk",
                        "query_id": query_id,
                        "query": query.get("query"),
                        "top_k_predictions": top_ids,
                        "relevant_truth": [item[0] for item in relevant_pairs[:5]],
                    }
                )

        if has_relevant and top_ids and top1_label < relevance_threshold:
            error_counts["retrieval_top1_irrelevant"] += 1
            if len(samples) < sample_limit:
                samples.append(
                    {
                        "error_type": "retrieval_top1_irrelevant",
                        "query_id": query_id,
                        "query": query.get("query"),
                        "top1_nct_id": top_ids[0],
                        "top1_label": top1_label,
                        "best_relevant_nct_id": relevant_pairs[0][0],
                    }
                )

    return dict(error_counts), samples


def _index_rules(rules: List[Dict[str, Any]]) -> Dict[Tuple[str, str, str, str, str], Dict[str, Any]]:
    return {rule_signature(rule): rule for rule in rules}


def analyze_parsing_errors(
    trials: List[Dict[str, Any]],
    gold_rules_by_trial: Dict[str, List[Dict[str, Any]]],
    predicted_rules_by_trial: Dict[str, List[Dict[str, Any]]],
    *,
    sample_limit: int = 10,
) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
    error_counts: Counter[str] = Counter()
    samples: List[Dict[str, Any]] = []
    text_by_trial = {
        str(trial.get("nct_id") or "").strip(): str(trial.get("eligibility_text") or "")
        for trial in trials
    }

    trial_ids = sorted(set(gold_rules_by_trial) | set(predicted_rules_by_trial))
    for trial_id in trial_ids:
        gold_rules = gold_rules_by_trial.get(trial_id, [])
        predicted_rules = predicted_rules_by_trial.get(trial_id, [])
        gold_index = _index_rules(gold_rules)
        pred_index = _index_rules(predicted_rules)
        gold_set = set(gold_index)
        pred_set = set(pred_index)

        for sig in sorted(gold_set - pred_set):
            error_type = f"parse_false_negative:{sig[1] or 'unknown'}"
            error_counts[error_type] += 1
            if len(samples) < sample_limit:
                rule = gold_index[sig]
                samples.append(
                    {
                        "error_type": error_type,
                        "nct_id": trial_id,
                        "rule": {
                            "type": sig[0],
                            "field": sig[1],
                            "operator": sig[2],
                            "value": sig[3],
                            "unit": sig[4],
                        },
                        "evidence_text": rule.get("evidence_text"),
                    }
                )

        for sig in sorted(pred_set - gold_set):
            error_type = f"parse_false_positive:{sig[1] or 'unknown'}"
            error_counts[error_type] += 1
            if len(samples) < sample_limit:
                rule = pred_index[sig]
                samples.append(
                    {
                        "error_type": error_type,
                        "nct_id": trial_id,
                        "rule": {
                            "type": sig[0],
                            "field": sig[1],
                            "operator": sig[2],
                            "value": sig[3],
                            "unit": sig[4],
                        },
                        "evidence_text": rule.get("evidence_text"),
                    }
                )

        eligibility_norm = _norm_text(text_by_trial.get(trial_id, ""))
        for rule in predicted_rules:
            evidence = _norm_text(str(rule.get("evidence_text") or ""))
            if evidence and evidence in eligibility_norm:
                continue
            error_counts["hallucinated_evidence"] += 1
            if len(samples) < sample_limit:
                samples.append(
                    {
                        "error_type": "hallucinated_evidence",
                        "nct_id": trial_id,
                        "rule_field": rule.get("field"),
                        "evidence_text": rule.get("evidence_text"),
                    }
                )

    return dict(error_counts), samples


def _metric_status(name: str, value: float) -> str:
    if name == "hallucination_rate":
        return "PASS" if value <= THRESHOLDS[name] else "FAIL"
    threshold = THRESHOLDS[name]
    return "PASS" if value >= threshold else "FAIL"


def build_recommendations(metrics: Dict[str, Any], error_counts: Dict[str, int]) -> List[str]:
    recs: List[str] = []
    retrieval = metrics["retrieval"]
    parsing = metrics["parsing"]
    hallucination = metrics["hallucination"]

    if retrieval["top_k_hitrate"] < THRESHOLDS["top_k_hitrate"]:
        recs.append(
            "Increase retrieval recall: enrich condition synonym expansion and combine title + eligibility weighted matching."
        )
    if parsing["f1"] < THRESHOLDS["parsing_f1"]:
        recs.append(
            "Improve parser coverage: prioritize rules for missing high-frequency fields shown in parse false negatives."
        )
    if hallucination["hallucination_rate"] > THRESHOLDS["hallucination_rate"]:
        recs.append(
            "Tighten evidence guardrails: reject rules when evidence_text cannot be aligned to source eligibility text."
        )
    if not recs:
        recs.append("Metrics pass configured thresholds; continue with larger holdout validation.")

    if error_counts:
        top_error = max(error_counts.items(), key=lambda item: item[1])[0]
        recs.append(f"Top observed error type is `{top_error}`; prioritize it first in M5 parser iteration.")
    return recs


def render_markdown(report: Dict[str, Any]) -> str:
    metric_rows = [
        (
            "Top-10 HitRate",
            report["metrics"]["retrieval"]["top_k_hitrate"],
            THRESHOLDS["top_k_hitrate"],
            _metric_status("top_k_hitrate", report["metrics"]["retrieval"]["top_k_hitrate"]),
        ),
        (
            "nDCG@10",
            report["metrics"]["retrieval"]["ndcg_at_k"],
            "-",
            "INFO",
        ),
        (
            "Parsing F1",
            report["metrics"]["parsing"]["f1"],
            THRESHOLDS["parsing_f1"],
            _metric_status("parsing_f1", report["metrics"]["parsing"]["f1"]),
        ),
        (
            "Hallucination Rate",
            report["metrics"]["hallucination"]["hallucination_rate"],
            THRESHOLDS["hallucination_rate"],
            _metric_status(
                "hallucination_rate",
                report["metrics"]["hallucination"]["hallucination_rate"],
            ),
        ),
    ]

    lines: List[str] = []
    lines.append("# M4 Evaluation Report")
    lines.append("")
    lines.append(f"- generated_at_utc: {report['generated_at_utc']}")
    lines.append(f"- query_count: {report['dataset']['query_count']}")
    lines.append(f"- trial_count: {report['dataset']['trial_count']}")
    lines.append(f"- relevance_pair_count: {report['dataset']['relevance_pair_count']}")
    lines.append(
        f"- retrieval_evaluated_queries: {report['metrics']['retrieval'].get('evaluated_queries', 0)}"
    )
    lines.append(
        f"- retrieval_skipped_queries: {report['metrics']['retrieval'].get('skipped_queries', 0)}"
    )
    lines.append("")
    lines.append("## Metric Summary")
    lines.append("")
    lines.append("| Metric | Value | Target | Status |")
    lines.append("| --- | ---: | ---: | :---: |")
    for metric_name, value, target, status in metric_rows:
        lines.append(f"| {metric_name} | {value} | {target} | {status} |")
    lines.append("")
    lines.append("## Error Type Breakdown")
    lines.append("")
    lines.append("| Error Type | Count |")
    lines.append("| --- | ---: |")
    if report["error_summary"]:
        for error_type, count in sorted(
            report["error_summary"].items(), key=lambda item: (-item[1], item[0])
        ):
            lines.append(f"| {error_type} | {count} |")
    else:
        lines.append("| none | 0 |")
    lines.append("")

    lines.append("## Error Samples")
    lines.append("")
    if report["error_samples"]:
        for idx, sample in enumerate(report["error_samples"], start=1):
            lines.append(f"{idx}. `{sample['error_type']}` - {json.dumps(sample, ensure_ascii=False)}")
    else:
        lines.append("No error samples captured.")
    lines.append("")

    lines.append("## Recommendations")
    lines.append("")
    for idx, rec in enumerate(report["recommendations"], start=1):
        lines.append(f"{idx}. {rec}")
    lines.append("")
    return "\n".join(lines)


def generate_report(
    *,
    queries_path: Path,
    trials_path: Path,
    relevance_path: Path,
    top_k: int,
    relevance_threshold: int,
    retrieval_results_path: str,
    predicted_rules_path: str,
    error_sample_limit: int = 10,
) -> Dict[str, Any]:
    queries = load_jsonl(queries_path)
    trials = load_jsonl(trials_path)
    relevance_rows = load_jsonl(relevance_path)
    relevance_index = build_relevance_index(relevance_rows)

    if retrieval_results_path:
        rankings = load_retrieval_rankings(Path(retrieval_results_path))
    else:
        rankings = build_heuristic_rankings(queries, trials)

    metrics = run_evaluation(
        queries_path=queries_path,
        trials_path=trials_path,
        relevance_path=relevance_path,
        top_k=top_k,
        relevance_threshold=relevance_threshold,
        retrieval_results_path=retrieval_results_path,
        predicted_rules_path=predicted_rules_path,
    )

    retrieval_errors, retrieval_samples = analyze_retrieval_errors(
        queries,
        rankings,
        relevance_index,
        top_k=top_k,
        relevance_threshold=relevance_threshold,
        sample_limit=error_sample_limit,
    )

    gold_rules = _load_gold_rules(trials)
    predicted_rules = generate_predicted_rules(trials, predicted_rules_path)
    parsing_errors, parsing_samples = analyze_parsing_errors(
        trials,
        gold_rules,
        predicted_rules,
        sample_limit=error_sample_limit,
    )

    merged_errors: Counter[str] = Counter()
    merged_errors.update(retrieval_errors)
    merged_errors.update(parsing_errors)
    merged_samples = retrieval_samples + parsing_samples
    merged_samples = merged_samples[:error_sample_limit]

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "query_count": len(queries),
            "trial_count": len(trials),
            "relevance_pair_count": len(relevance_rows),
        },
        "metrics": metrics,
        "error_summary": dict(merged_errors),
        "error_samples": merged_samples,
        "recommendations": build_recommendations(metrics, dict(merged_errors)),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate M4 evaluation report.")
    parser.add_argument("--queries", default="eval/data/queries.jsonl")
    parser.add_argument("--trials", default="eval/data/trials_sample.jsonl")
    parser.add_argument("--relevance", default="eval/annotations/relevance.annotator_a.jsonl")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--relevance-threshold", type=int, default=1)
    parser.add_argument("--retrieval-results", default="")
    parser.add_argument("--predicted-rules", default="")
    parser.add_argument("--error-sample-limit", type=int, default=10)
    parser.add_argument(
        "--output-md",
        default="eval/reports/m4_evaluation_report.md",
        help="Markdown report output path",
    )
    parser.add_argument(
        "--output-json",
        default="eval/reports/m4_evaluation_report.json",
        help="JSON report output path",
    )
    args = parser.parse_args()

    report = generate_report(
        queries_path=Path(args.queries),
        trials_path=Path(args.trials),
        relevance_path=Path(args.relevance),
        top_k=args.top_k,
        relevance_threshold=args.relevance_threshold,
        retrieval_results_path=args.retrieval_results,
        predicted_rules_path=args.predicted_rules,
        error_sample_limit=args.error_sample_limit,
    )

    output_md = Path(args.output_md)
    output_json = Path(args.output_json)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)

    markdown = render_markdown(report)
    output_md.write_text(markdown, encoding="utf-8")
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(markdown)


if __name__ == "__main__":
    main()
