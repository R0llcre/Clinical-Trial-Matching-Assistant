from __future__ import annotations

import json
from pathlib import Path

import pytest

from run_evaluation import (
    compute_relevance_coverage,
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
    assert metrics["evaluated_queries"] == 1
    assert metrics["skipped_queries"] == 0


def test_compute_retrieval_metrics_skips_query_without_relevant() -> None:
    query_ids = ["Q1", "Q2"]
    rankings = {"Q1": ["N1"], "Q2": ["N2"]}
    relevance = {("Q1", "N1"): 2, ("Q2", "N2"): 0}

    metrics = compute_retrieval_metrics(
        query_ids,
        rankings,
        relevance,
        top_k=1,
        relevant_threshold=1,
    )

    assert metrics["evaluated_queries"] == 1
    assert metrics["skipped_queries"] == 1


def test_compute_relevance_coverage_counts_full_partial_and_empty_queries() -> None:
    query_ids = ["Q1", "Q2"]
    candidate_nct_ids = ["N1", "N2"]
    relevance = {
        ("Q1", "N1"): 2,
        ("Q1", "N2"): 0,
        ("Q2", "N1"): 1,
    }

    metrics = compute_relevance_coverage(query_ids, candidate_nct_ids, relevance)
    assert metrics["candidate_pool_size"] == 2
    assert metrics["total_pairs"] == 4
    assert metrics["annotated_pairs"] == 3
    assert metrics["annotation_coverage"] == pytest.approx(0.75)
    assert metrics["fully_annotated_queries"] == 1
    assert metrics["partially_annotated_queries"] == 1
    assert metrics["unannotated_queries"] == 0


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


def test_run_evaluation_rejects_low_relevance_coverage(tmp_path: Path) -> None:
    queries_path = tmp_path / "queries.jsonl"
    trials_path = tmp_path / "trials.jsonl"
    relevance_path = tmp_path / "relevance.jsonl"
    predicted_rules_path = tmp_path / "predicted_rules.jsonl"

    queries_path.write_text(
        json.dumps({"query_id": "Q1", "query": "diabetes", "expected_conditions": ["diabetes"]})
        + "\n",
        encoding="utf-8",
    )
    trials_path.write_text(
        json.dumps(
            {
                "nct_id": "N1",
                "title": "Diabetes trial",
                "eligibility_text": "Adults only.",
                "labeled_rules": [],
            }
        )
        + "\n"
        + json.dumps(
            {
                "nct_id": "N2",
                "title": "Asthma trial",
                "eligibility_text": "Adults only.",
                "labeled_rules": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    relevance_path.write_text(
        json.dumps({"query_id": "Q1", "nct_id": "N1", "relevance_label": 2}) + "\n",
        encoding="utf-8",
    )
    predicted_rules_path.write_text(
        json.dumps({"nct_id": "N1", "predicted_rules": []}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="coverage below minimum"):
        run_evaluation(
            queries_path=queries_path,
            trials_path=trials_path,
            relevance_path=relevance_path,
            min_relevance_coverage=1.0,
            predicted_rules_path=str(predicted_rules_path),
        )
