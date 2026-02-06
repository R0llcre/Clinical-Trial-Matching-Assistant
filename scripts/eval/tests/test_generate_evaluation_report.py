from __future__ import annotations

import json
from pathlib import Path

from generate_evaluation_report import (
    analyze_retrieval_errors,
    generate_report,
    render_markdown,
)


def test_analyze_retrieval_errors_detects_miss_and_top1() -> None:
    queries = [{"query_id": "Q1", "query": "diabetes"}]
    rankings = {"Q1": ["N0", "N2", "N1"]}
    relevance = {("Q1", "N0"): 0, ("Q1", "N1"): 2, ("Q1", "N2"): 0}
    counts, samples = analyze_retrieval_errors(
        queries,
        rankings,
        relevance,
        top_k=2,
        relevance_threshold=1,
        sample_limit=5,
    )

    assert counts["retrieval_miss_topk"] == 1
    assert counts["retrieval_top1_irrelevant"] == 1
    assert len(samples) >= 1


def test_render_markdown_contains_required_sections() -> None:
    report = {
        "generated_at_utc": "2026-02-06T00:00:00+00:00",
        "dataset": {"query_count": 1, "trial_count": 1, "relevance_pair_count": 1},
        "metrics": {
            "retrieval": {"top_k_hitrate": 0.8, "ndcg_at_k": 0.7},
            "parsing": {"f1": 0.6},
            "hallucination": {"hallucination_rate": 0.01},
        },
        "error_summary": {"retrieval_miss_topk": 1},
        "error_samples": [{"error_type": "retrieval_miss_topk", "query_id": "Q1"}],
        "recommendations": ["Improve retrieval recall."],
    }

    markdown = render_markdown(report)
    assert "## Metric Summary" in markdown
    assert "## Error Type Breakdown" in markdown
    assert "## Error Samples" in markdown
    assert "## Recommendations" in markdown


def test_generate_report_smoke(tmp_path: Path) -> None:
    queries_path = tmp_path / "queries.jsonl"
    trials_path = tmp_path / "trials.jsonl"
    relevance_path = tmp_path / "relevance.jsonl"
    predicted_rules_path = tmp_path / "predicted.jsonl"

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
                "labeled_rules": [
                    {
                        "type": "INCLUSION",
                        "field": "other",
                        "operator": "EXISTS",
                        "value": None,
                        "unit": None,
                        "evidence_text": "Adults only.",
                    }
                ],
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
        json.dumps(
            {
                "nct_id": "N1",
                "predicted_rules": [
                    {
                        "type": "INCLUSION",
                        "field": "other",
                        "operator": "EXISTS",
                        "value": None,
                        "unit": None,
                        "evidence_text": "Adults only.",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = generate_report(
        queries_path=queries_path,
        trials_path=trials_path,
        relevance_path=relevance_path,
        top_k=10,
        relevance_threshold=1,
        retrieval_results_path="",
        predicted_rules_path=str(predicted_rules_path),
        error_sample_limit=5,
    )

    assert "metrics" in report
    assert "error_summary" in report
    assert "recommendations" in report
