from __future__ import annotations

import json
from pathlib import Path

import pytest

from run_evaluation import (
    compute_hallucination_rate,
    compute_parse_metrics,
    compute_retrieval_metrics,
    ndcg_at_k,
    rule_signature,
    run_evaluation,
)


def test_ndcg_at_k_perfect_ranking() -> None:
    score = ndcg_at_k([2, 1, 0], 3)
    assert score == pytest.approx(1.0)


def test_compute_retrieval_metrics_simple_case() -> None:
    query_ids = ["Q1"]
    rankings = {"Q1": ["N1", "N2", "N3"]}
    relevance = {("Q1", "N1"): 0, ("Q1", "N2"): 2, ("Q1", "N3"): 1}

    metrics = compute_retrieval_metrics(
        query_ids,
        rankings,
        relevance,
        top_k=2,
        relevant_threshold=1,
    )

    assert metrics["top_k_hitrate"] == pytest.approx(1.0)
    assert 0.0 <= metrics["ndcg_at_k"] <= 1.0


def test_rule_signature_normalizes_value_and_unit() -> None:
    signature = rule_signature(
        {
            "type": "inclusion",
            "field": "Age",
            "operator": ">=",
            "value": 18.0,
            "unit": "Years",
        }
    )
    assert signature == ("INCLUSION", "age", ">=", "18", "years")


def test_compute_parse_metrics_counts_tp_fp_fn() -> None:
    gold = {
        "N1": [
            {
                "type": "INCLUSION",
                "field": "age",
                "operator": ">=",
                "value": 18,
                "unit": "years",
            }
        ]
    }
    predicted = {
        "N1": [
            {
                "type": "INCLUSION",
                "field": "age",
                "operator": ">=",
                "value": 18,
                "unit": "years",
            },
            {
                "type": "INCLUSION",
                "field": "sex",
                "operator": "=",
                "value": "female",
                "unit": None,
            },
        ]
    }
    metrics = compute_parse_metrics(gold, predicted)
    assert metrics["tp"] == 1
    assert metrics["fp"] == 1
    assert metrics["fn"] == 0
    assert metrics["precision"] == pytest.approx(0.5)


def test_compute_hallucination_rate_uses_evidence_alignment() -> None:
    trials = [{"nct_id": "N1", "eligibility_text": "Adults 18 years or older."}]
    predicted = {
        "N1": [
            {"evidence_text": "Adults 18 years or older."},
            {"evidence_text": "Unrelated sentence"},
        ]
    }
    metrics = compute_hallucination_rate(trials, predicted)
    assert metrics["total_predicted_rules"] == 2
    assert metrics["hallucinated_rules"] == 1
    assert metrics["hallucination_rate"] == pytest.approx(0.5)


def test_run_evaluation_repo_data_with_custom_predicted_rules(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    predicted_rules_path = tmp_path / "predicted_rules.jsonl"
    predicted_rows = [
        {
            "nct_id": "NCT90000001",
            "predicted_rules": [
                {
                    "type": "INCLUSION",
                    "field": "age",
                    "operator": ">=",
                    "value": 18,
                    "unit": "years",
                    "evidence_text": "Participants must be 18 years or older.",
                }
            ],
        }
    ]
    with predicted_rules_path.open("w", encoding="utf-8") as handle:
        for row in predicted_rows:
            handle.write(json.dumps(row))
            handle.write("\n")

    output = run_evaluation(
        queries_path=repo_root / "eval" / "data" / "queries.jsonl",
        trials_path=repo_root / "eval" / "data" / "trials_sample.jsonl",
        relevance_path=repo_root / "eval" / "annotations" / "relevance.annotator_a.jsonl",
        predicted_rules_path=str(predicted_rules_path),
    )
    assert "retrieval" in output
    assert "parsing" in output
    assert "hallucination" in output
