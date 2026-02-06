from __future__ import annotations

import json
from pathlib import Path

from generate_retrieval_only_report import build_report, render_markdown


def test_build_report_computes_dataset_and_agreement(tmp_path: Path) -> None:
    a_path = tmp_path / "a.jsonl"
    b_path = tmp_path / "b.jsonl"

    a_rows = [
        {"query_id": "Q1", "nct_id": "N1", "relevance_label": 2},
        {"query_id": "Q1", "nct_id": "N2", "relevance_label": 0},
        {"query_id": "Q2", "nct_id": "N1", "relevance_label": 1},
    ]
    b_rows = [
        {"query_id": "Q1", "nct_id": "N1", "relevance_label": 2},
        {"query_id": "Q1", "nct_id": "N2", "relevance_label": 1},
        {"query_id": "Q2", "nct_id": "N1", "relevance_label": 1},
    ]
    a_path.write_text("".join(json.dumps(row) + "\n" for row in a_rows), encoding="utf-8")
    b_path.write_text("".join(json.dumps(row) + "\n" for row in b_rows), encoding="utf-8")

    report = build_report(annotator_a_path=a_path, annotator_b_path=b_path)

    assert report["dataset"]["total_pairs"] == 3
    assert report["dataset"]["query_count"] == 2
    assert report["dataset"]["nct_count"] == 2
    assert report["dataset"]["label_distribution"] == {"0": 1, "1": 1, "2": 1}
    assert report["agreement"]["overlap_pairs"] == 3
    assert report["agreement"]["exact_match_rate"] == 0.6667
    assert report["agreement"]["cohen_kappa"] == 0.5


def test_render_markdown_contains_sections(tmp_path: Path) -> None:
    a_path = tmp_path / "a.jsonl"
    rows = [
        {"query_id": "Q1", "nct_id": "N1", "relevance_label": 2},
        {"query_id": "Q1", "nct_id": "N2", "relevance_label": 0},
    ]
    a_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    report = build_report(annotator_a_path=a_path, annotator_b_path=None)

    markdown = render_markdown(report)
    assert "# Retrieval Annotation Report" in markdown
    assert "## Label Distribution" in markdown
    assert "## Query Breakdown" in markdown
