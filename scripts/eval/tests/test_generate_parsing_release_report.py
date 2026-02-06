from __future__ import annotations

from generate_parsing_release_report import build_report, render_markdown


def test_build_report_computes_dataset_and_metrics() -> None:
    trials = [
        {
            "nct_id": "N1",
            "eligibility_text": "Adults age 18 years and older.",
            "labeled_rules": [
                {
                    "type": "INCLUSION",
                    "field": "age",
                    "operator": ">=",
                    "value": 18,
                    "unit": "years",
                    "evidence_text": "Adults age 18 years and older.",
                }
            ],
        }
    ]
    predicted_rules_by_trial = {
        "N1": [
            {
                "type": "INCLUSION",
                "field": "age",
                "operator": ">=",
                "value": 18,
                "unit": "years",
                "evidence_text": "Adults age 18 years and older.",
            }
        ]
    }

    report = build_report(
        trials=trials,
        predicted_rules_by_trial=predicted_rules_by_trial,
    )

    assert report["dataset"]["trial_count"] == 1
    assert report["dataset"]["gold_rule_count"] == 1
    assert report["dataset"]["unique_fields"] == 1
    assert report["metrics"]["parsing"]["f1"] == 1.0
    assert report["metrics"]["hallucination"]["hallucination_rate"] == 0.0


def test_render_markdown_contains_sections() -> None:
    report = {
        "generated_at_utc": "2026-02-06T00:00:00+00:00",
        "dataset": {
            "trial_count": 100,
            "gold_rule_count": 525,
            "unique_fields": 7,
            "rules_per_trial": {"min": 0, "median": 4.0, "max": 16},
            "field_distribution": {"age": 141, "condition": 221},
        },
        "metrics": {
            "parsing": {"precision": 0.39, "recall": 0.32, "f1": 0.35},
            "hallucination": {"hallucination_rate": 0.0},
        },
    }

    markdown = render_markdown(report)
    assert "# Parsing Release Report" in markdown
    assert "## Metric Summary" in markdown
    assert "## Field Distribution" in markdown
