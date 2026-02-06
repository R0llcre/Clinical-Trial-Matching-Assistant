from __future__ import annotations

from check_m4_release_gate import build_release_gate_report, render_markdown


def _thresholds() -> dict[str, float]:
    return {
        "smoke_top10_hitrate": 0.7,
        "smoke_parsing_f1": 0.8,
        "smoke_hallucination_rate_max": 0.02,
        "smoke_relevance_coverage": 1.0,
        "release_query_count_min": 10.0,
        "release_total_pairs_min": 1500.0,
        "release_label2_count_min": 60.0,
        "release_queries_with_label2_min": 6.0,
        "release_min_pairs_per_query": 120.0,
    }


def _smoke_report() -> dict[str, object]:
    return {
        "metrics": {
            "retrieval": {
                "top_k_hitrate": 1.0,
                "annotation_coverage": 1.0,
            },
            "parsing": {"f1": 1.0},
            "hallucination": {"hallucination_rate": 0.0},
        }
    }


def _retrieval_report_pass() -> dict[str, object]:
    query_breakdown = []
    for idx in range(10):
        query_breakdown.append(
            {
                "query_id": f"Q{idx + 1:04d}",
                "pair_count": 160,
                "relevant_count_eq2": 8 if idx < 7 else 0,
            }
        )
    return {
        "dataset": {
            "query_count": 10,
            "total_pairs": 1600,
            "label_distribution": {"0": 300, "1": 1240, "2": 60},
        },
        "query_breakdown": query_breakdown,
    }


def test_build_release_gate_report_passes() -> None:
    report = build_release_gate_report(
        smoke_report=_smoke_report(),
        retrieval_report=_retrieval_report_pass(),
        thresholds=_thresholds(),
    )
    assert report["overall_status"] == "PASS"
    assert report["gate_status"]["smoke"] == "PASS"
    assert report["gate_status"]["release"] == "PASS"


def test_build_release_gate_report_fails_release_constraints() -> None:
    retrieval_report = _retrieval_report_pass()
    retrieval_report["dataset"]["total_pairs"] = 1100
    retrieval_report["dataset"]["label_distribution"]["2"] = 10
    report = build_release_gate_report(
        smoke_report=_smoke_report(),
        retrieval_report=retrieval_report,
        thresholds=_thresholds(),
    )

    assert report["overall_status"] == "FAIL"
    assert report["gate_status"]["smoke"] == "PASS"
    assert report["gate_status"]["release"] == "FAIL"
    failed_checks = {check["id"] for check in report["checks"] if check["status"] == "FAIL"}
    assert "release.total_pairs" in failed_checks
    assert "release.label2_total" in failed_checks


def test_render_markdown_contains_gate_sections() -> None:
    report = build_release_gate_report(
        smoke_report=_smoke_report(),
        retrieval_report=_retrieval_report_pass(),
        thresholds=_thresholds(),
    )
    markdown = render_markdown(report)
    assert "# M4 Release Gate Report" in markdown
    assert "## Gate Summary" in markdown
    assert "## Check Details" in markdown
