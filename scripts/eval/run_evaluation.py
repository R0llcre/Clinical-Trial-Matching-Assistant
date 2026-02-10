#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


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


def dump_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _norm_text(text: str) -> str:
    return " ".join((text or "").lower().replace("-", " ").split())


def _tokenize(text: str) -> set[str]:
    return {token for token in _norm_text(text).split() if len(token) > 2}


def _heuristic_trial_score(query: Dict[str, Any], trial: Dict[str, Any]) -> float:
    expected_conditions = query.get("expected_conditions") or []
    condition_text = " ".join(str(item) for item in expected_conditions if isinstance(item, str))
    query_text = str(query.get("query") or "")

    title = str(trial.get("title") or "")
    eligibility = str(trial.get("eligibility_text") or "")
    trial_text = f"{title} {eligibility}"
    trial_tokens = _tokenize(trial_text)

    score = 0.0

    if condition_text:
        c_norm = _norm_text(condition_text)
        t_norm = _norm_text(trial_text)
        if c_norm and c_norm in t_norm:
            score += 10.0
        overlap = len(_tokenize(c_norm) & trial_tokens)
        score += overlap * 1.5

    query_tokens = _tokenize(query_text)
    score += len(query_tokens & trial_tokens) * 0.5

    return score


def build_heuristic_rankings(
    queries: Sequence[Dict[str, Any]], trials: Sequence[Dict[str, Any]]
) -> Dict[str, List[str]]:
    rankings: Dict[str, List[str]] = {}
    for query in queries:
        query_id = str(query.get("query_id") or "").strip()
        if not query_id:
            continue
        scored: List[Tuple[float, str]] = []
        for trial in trials:
            nct_id = str(trial.get("nct_id") or "").strip()
            if not nct_id:
                continue
            score = _heuristic_trial_score(query, trial)
            scored.append((score, nct_id))
        scored.sort(key=lambda item: (-item[0], item[1]))
        rankings[query_id] = [nct_id for _, nct_id in scored]
    return rankings


def load_retrieval_rankings(path: Path) -> Dict[str, List[str]]:
    rows = load_jsonl(path)
    rankings: Dict[str, List[str]] = {}
    for row in rows:
        query_id = str(row.get("query_id") or "").strip()
        ranked_nct_ids = row.get("ranked_nct_ids")
        if not query_id or not isinstance(ranked_nct_ids, list):
            raise ValueError(
                f"{path}: each row must contain query_id and ranked_nct_ids list"
            )
        normalized = [
            str(item).strip()
            for item in ranked_nct_ids
            if isinstance(item, str) and str(item).strip()
        ]
        rankings[query_id] = normalized
    return rankings


def build_relevance_index(
    rows: Sequence[Dict[str, Any]],
) -> Dict[Tuple[str, str], int]:
    relevance: Dict[Tuple[str, str], int] = {}
    for row in rows:
        query_id = str(row.get("query_id") or "").strip()
        nct_id = str(row.get("nct_id") or "").strip()
        label = row.get("relevance_label")
        if not query_id or not nct_id:
            continue
        if isinstance(label, bool) or not isinstance(label, int):
            continue
        relevance[(query_id, nct_id)] = label
    return relevance


def compute_relevance_coverage(
    query_ids: Sequence[str],
    candidate_nct_ids: Sequence[str],
    relevance: Dict[Tuple[str, str], int],
) -> Dict[str, Any]:
    unique_query_ids = sorted({query_id for query_id in query_ids if query_id})
    unique_nct_ids = sorted({nct_id for nct_id in candidate_nct_ids if nct_id})
    total_pairs = len(unique_query_ids) * len(unique_nct_ids)
    if total_pairs == 0:
        return {
            "candidate_pool_size": len(unique_nct_ids),
            "total_pairs": 0,
            "annotated_pairs": 0,
            "annotation_coverage": 0.0,
            "fully_annotated_queries": 0,
            "partially_annotated_queries": 0,
            "unannotated_queries": 0,
        }

    fully_annotated = 0
    partially_annotated = 0
    unannotated = 0
    annotated_pairs = 0

    for query_id in unique_query_ids:
        query_annotated = sum(
            1
            for nct_id in unique_nct_ids
            if (query_id, nct_id) in relevance
        )
        annotated_pairs += query_annotated
        if query_annotated == len(unique_nct_ids):
            fully_annotated += 1
        elif query_annotated == 0:
            unannotated += 1
        else:
            partially_annotated += 1

    coverage = annotated_pairs / total_pairs
    return {
        "candidate_pool_size": len(unique_nct_ids),
        "total_pairs": total_pairs,
        "annotated_pairs": annotated_pairs,
        "annotation_coverage": round(coverage, 4),
        "fully_annotated_queries": fully_annotated,
        "partially_annotated_queries": partially_annotated,
        "unannotated_queries": unannotated,
    }


def dcg_at_k(relevances: Sequence[int], k: int) -> float:
    if k <= 0:
        return 0.0
    score = 0.0
    for idx, rel in enumerate(relevances[:k], start=1):
        gain = (2**max(rel, 0)) - 1
        score += gain / math.log2(idx + 1)
    return score


def ndcg_at_k(relevances: Sequence[int], k: int) -> float:
    ideal = sorted(relevances, reverse=True)
    ideal_dcg = dcg_at_k(ideal, k)
    if ideal_dcg == 0.0:
        return 0.0
    return dcg_at_k(relevances, k) / ideal_dcg


def compute_retrieval_metrics(
    query_ids: Sequence[str],
    rankings: Dict[str, List[str]],
    relevance: Dict[Tuple[str, str], int],
    *,
    top_k: int = 10,
    relevant_threshold: int = 1,
    ignore_queries_without_relevant: bool = True,
) -> Dict[str, float]:
    if not query_ids:
        return {
            "top_k_hitrate": 0.0,
            "ndcg_at_k": 0.0,
            "evaluated_queries": 0,
            "skipped_queries": 0,
        }

    hit_count = 0
    ndcgs: List[float] = []
    evaluated_queries = 0

    for query_id in query_ids:
        ranked = rankings.get(query_id, [])
        rels = [int(relevance.get((query_id, nct_id), 0)) for nct_id in ranked]
        annotated_rels = [
            int(relevance[(query_id, nct_id)])
            for nct_id in ranked
            if (query_id, nct_id) in relevance
        ]
        has_relevant = any(rel >= relevant_threshold for rel in annotated_rels)
        if ignore_queries_without_relevant and not has_relevant:
            continue

        evaluated_queries += 1
        rels_for_hit = rels[:top_k]

        if any(rel >= relevant_threshold for rel in rels_for_hit):
            hit_count += 1

        # Add known-but-unranked annotated items as zeros is not needed for nDCG ratio.
        ndcgs.append(ndcg_at_k(rels, top_k))

    if evaluated_queries == 0:
        return {
            "top_k_hitrate": 0.0,
            "ndcg_at_k": 0.0,
            "evaluated_queries": 0,
            "skipped_queries": len(query_ids),
        }

    hitrate = hit_count / evaluated_queries
    avg_ndcg = sum(ndcgs) / len(ndcgs)
    return {
        "top_k_hitrate": round(hitrate, 4),
        "ndcg_at_k": round(avg_ndcg, 4),
        "evaluated_queries": evaluated_queries,
        "skipped_queries": len(query_ids) - evaluated_queries,
    }


def _normalize_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)
    if isinstance(value, str):
        return _norm_text(value)
    if isinstance(value, list):
        normalized = sorted(_normalize_value(item) for item in value)
        return "|".join(normalized)
    return _norm_text(str(value))


def rule_signature(rule: Dict[str, Any]) -> Tuple[str, str, str, str, str]:
    rule_type = str(rule.get("type") or "").upper()
    field = _norm_text(str(rule.get("field") or ""))
    operator = str(rule.get("operator") or "").upper()
    value = _normalize_value(rule.get("value"))
    unit = _norm_text(str(rule.get("unit") or ""))
    return (rule_type, field, operator, value, unit)


def _is_unparsed_placeholder_rule(rule: Dict[str, Any]) -> bool:
    """Return True for v1 placeholder rules that encode 'unparsed ... criteria'.

    These rules are intentionally emitted as UNKNOWN coverage hints for matching UX,
    but they do not exist in gold datasets and should not be scored as false positives
    in parsing F1. We treat them as separate coverage signals.
    """
    if not isinstance(rule, dict):
        return False
    field = _norm_text(str(rule.get("field") or ""))
    operator = str(rule.get("operator") or "").upper()
    value = rule.get("value")
    if field != "other" or operator != "EXISTS":
        return False
    if not isinstance(value, str):
        return False
    return _norm_text(value).startswith("unparsed")


def _load_gold_rules(trials: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for trial in trials:
        nct_id = str(trial.get("nct_id") or "").strip()
        rules = trial.get("labeled_rules")
        if not nct_id:
            continue
        if not isinstance(rules, list):
            rules = []
        out[nct_id] = [rule for rule in rules if isinstance(rule, dict)]
    return out


def _import_parser() -> Any:
    repo_root = Path(__file__).resolve().parents[2]
    worker_root = repo_root / "apps" / "worker"
    if str(worker_root) not in sys.path:
        sys.path.insert(0, str(worker_root))
    try:
        from services.eligibility_parser import parse_criteria_v1
    except ImportError as exc:
        raise RuntimeError(
            "cannot import parse_criteria_v1 from apps/worker/services/eligibility_parser.py"
        ) from exc
    return parse_criteria_v1


def _load_predicted_rules_from_jsonl(path: Path) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    rows = load_jsonl(path)
    for row in rows:
        nct_id = str(row.get("nct_id") or "").strip()
        rules = row.get("predicted_rules")
        if not nct_id or not isinstance(rules, list):
            continue
        out[nct_id] = [rule for rule in rules if isinstance(rule, dict)]
    return out


def generate_predicted_rules(
    trials: Sequence[Dict[str, Any]], predicted_rules_path: str
) -> Dict[str, List[Dict[str, Any]]]:
    if predicted_rules_path:
        return _load_predicted_rules_from_jsonl(Path(predicted_rules_path))

    parse_criteria_v1 = _import_parser()
    predictions: Dict[str, List[Dict[str, Any]]] = {}
    for trial in trials:
        nct_id = str(trial.get("nct_id") or "").strip()
        text = str(trial.get("eligibility_text") or "")
        if not nct_id:
            continue
        predictions[nct_id] = parse_criteria_v1(text)
    return predictions


def compute_parse_metrics(
    gold_rules_by_trial: Dict[str, List[Dict[str, Any]]],
    predicted_rules_by_trial: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, float]:
    true_positive = 0
    false_positive = 0
    false_negative = 0
    placeholder_predicted = 0

    trial_ids = sorted(set(gold_rules_by_trial) | set(predicted_rules_by_trial))
    for trial_id in trial_ids:
        gold_set = {rule_signature(rule) for rule in gold_rules_by_trial.get(trial_id, [])}
        pred_rules = predicted_rules_by_trial.get(trial_id, [])
        if pred_rules:
            placeholder_predicted += sum(
                1 for rule in pred_rules if _is_unparsed_placeholder_rule(rule)
            )
        pred_set = {
            rule_signature(rule)
            for rule in pred_rules
            if not _is_unparsed_placeholder_rule(rule)
        }
        true_positive += len(gold_set & pred_set)
        false_positive += len(pred_set - gold_set)
        false_negative += len(gold_set - pred_set)

    precision = (
        true_positive / (true_positive + false_positive)
        if (true_positive + false_positive)
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if (true_positive + false_negative)
        else 0.0
    )
    f1 = (
        (2 * precision * recall / (precision + recall))
        if (precision + recall)
        else 0.0
    )
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": true_positive,
        "fp": false_positive,
        "fn": false_negative,
        "placeholder_predicted_rules": placeholder_predicted,
    }


def compute_hallucination_rate(
    trials: Sequence[Dict[str, Any]],
    predicted_rules_by_trial: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, float]:
    text_by_id = {
        str(trial.get("nct_id") or "").strip(): str(trial.get("eligibility_text") or "")
        for trial in trials
    }
    total = 0
    hallucinated = 0
    placeholder_predicted = 0
    for nct_id, rules in predicted_rules_by_trial.items():
        eligibility = _norm_text(text_by_id.get(nct_id, ""))
        for rule in rules:
            if _is_unparsed_placeholder_rule(rule):
                placeholder_predicted += 1
                continue
            evidence = _norm_text(str(rule.get("evidence_text") or ""))
            total += 1
            if not evidence or evidence not in eligibility:
                hallucinated += 1
    rate = (hallucinated / total) if total else 0.0
    return {
        "hallucination_rate": round(rate, 4),
        "hallucinated_rules": hallucinated,
        "total_predicted_rules": total,
        "placeholder_predicted_rules": placeholder_predicted,
    }


def run_evaluation(
    *,
    queries_path: Path,
    trials_path: Path,
    relevance_path: Path,
    top_k: int = 10,
    relevance_threshold: int = 1,
    min_relevance_coverage: float = 0.0,
    retrieval_results_path: str = "",
    predicted_rules_path: str = "",
) -> Dict[str, Any]:
    queries = load_jsonl(queries_path)
    trials = load_jsonl(trials_path)
    relevance_rows = load_jsonl(relevance_path)
    relevance = build_relevance_index(relevance_rows)

    query_ids = [str(row.get("query_id") or "").strip() for row in queries]
    query_ids = [query_id for query_id in query_ids if query_id]
    candidate_nct_ids = [
        str(trial.get("nct_id") or "").strip()
        for trial in trials
        if str(trial.get("nct_id") or "").strip()
    ]

    if retrieval_results_path:
        rankings = load_retrieval_rankings(Path(retrieval_results_path))
    else:
        rankings = build_heuristic_rankings(queries, trials)

    coverage_metrics = compute_relevance_coverage(query_ids, candidate_nct_ids, relevance)
    if min_relevance_coverage > 0 and (
        coverage_metrics["annotation_coverage"] < min_relevance_coverage
    ):
        coverage_value = coverage_metrics["annotation_coverage"]
        raise ValueError(
            "relevance annotation coverage below minimum: "
            f"{coverage_value} < {min_relevance_coverage}"
        )

    retrieval_metrics = compute_retrieval_metrics(
        query_ids,
        rankings,
        relevance,
        top_k=top_k,
        relevant_threshold=relevance_threshold,
    )

    gold_rules = _load_gold_rules(trials)
    predicted_rules = generate_predicted_rules(trials, predicted_rules_path)
    parse_metrics = compute_parse_metrics(gold_rules, predicted_rules)
    hallucination_metrics = compute_hallucination_rate(trials, predicted_rules)

    return {
        "retrieval": {
            "top_k": top_k,
            "relevant_threshold": relevance_threshold,
            **retrieval_metrics,
            **coverage_metrics,
        },
        "parsing": parse_metrics,
        "hallucination": hallucination_metrics,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run M4 evaluation metrics.")
    parser.add_argument("--queries", default="eval/data/queries.jsonl")
    parser.add_argument("--trials", default="eval/data/trials_sample.jsonl")
    parser.add_argument("--relevance", default="eval/annotations/relevance.annotator_a.jsonl")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--relevance-threshold", type=int, default=1)
    parser.add_argument("--min-relevance-coverage", type=float, default=0.0)
    parser.add_argument(
        "--retrieval-results",
        default="",
        help="Optional JSONL with fields: query_id, ranked_nct_ids",
    )
    parser.add_argument(
        "--predicted-rules",
        default="",
        help="Optional JSONL with fields: nct_id, predicted_rules",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output file for JSON report",
    )
    args = parser.parse_args()

    if args.top_k < 1:
        raise ValueError("--top-k must be >= 1")

    result = run_evaluation(
        queries_path=Path(args.queries),
        trials_path=Path(args.trials),
        relevance_path=Path(args.relevance),
        top_k=args.top_k,
        relevance_threshold=args.relevance_threshold,
        min_relevance_coverage=args.min_relevance_coverage,
        retrieval_results_path=args.retrieval_results,
        predicted_rules_path=args.predicted_rules,
    )

    if args.output:
        dump_json(Path(args.output), result)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
