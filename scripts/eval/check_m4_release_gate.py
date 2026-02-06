#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must be a JSON object")
    return payload


def dump_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _check(
    *,
    check_id: str,
    source: str,
    comparator: str,
    actual: float,
    target: float,
) -> Dict[str, Any]:
    if comparator == ">=":
        passed = actual >= target
    elif comparator == "<=":
        passed = actual <= target
    else:
        raise ValueError(f"unsupported comparator: {comparator}")

    return {
        "id": check_id,
        "source": source,
        "comparator": comparator,
        "actual": round(actual, 4),
        "target": round(target, 4),
        "status": "PASS" if passed else "FAIL",
    }


def _require_number(payload: Dict[str, Any], key: str, context: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"missing or invalid numeric field `{key}` in {context}")
    return float(value)


def build_release_gate_report(
    *,
    smoke_report: Dict[str, Any],
    retrieval_report: Dict[str, Any],
    thresholds: Dict[str, float],
) -> Dict[str, Any]:
    metrics = smoke_report.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("smoke report missing `metrics`")

    smoke_retrieval = metrics.get("retrieval")
    smoke_parsing = metrics.get("parsing")
    smoke_hallucination = metrics.get("hallucination")
    if not isinstance(smoke_retrieval, dict):
        raise ValueError("smoke report missing `metrics.retrieval`")
    if not isinstance(smoke_parsing, dict):
        raise ValueError("smoke report missing `metrics.parsing`")
    if not isinstance(smoke_hallucination, dict):
        raise ValueError("smoke report missing `metrics.hallucination`")

    dataset = retrieval_report.get("dataset")
    query_breakdown = retrieval_report.get("query_breakdown")
    if not isinstance(dataset, dict):
        raise ValueError("retrieval report missing `dataset`")
    if not isinstance(query_breakdown, list):
        raise ValueError("retrieval report missing `query_breakdown`")

    label_distribution = dataset.get("label_distribution")
    if not isinstance(label_distribution, dict):
        raise ValueError("retrieval report missing `dataset.label_distribution`")

    label_2_count = float(int(label_distribution.get("2", 0)))
    query_with_label_2_count = float(
        sum(
            1
            for row in query_breakdown
            if isinstance(row, dict) and int(row.get("relevant_count_eq2", 0)) > 0
        )
    )
    min_pairs_per_query = float(
        min(
            int(row.get("pair_count", 0))
            for row in query_breakdown
            if isinstance(row, dict)
        )
    )

    checks: List[Dict[str, Any]] = [
        _check(
            check_id="smoke.top10_hitrate",
            source="m4_evaluation_report",
            comparator=">=",
            actual=_require_number(smoke_retrieval, "top_k_hitrate", "metrics.retrieval"),
            target=thresholds["smoke_top10_hitrate"],
        ),
        _check(
            check_id="smoke.parsing_f1",
            source="m4_evaluation_report",
            comparator=">=",
            actual=_require_number(smoke_parsing, "f1", "metrics.parsing"),
            target=thresholds["smoke_parsing_f1"],
        ),
        _check(
            check_id="smoke.hallucination_rate",
            source="m4_evaluation_report",
            comparator="<=",
            actual=_require_number(
                smoke_hallucination, "hallucination_rate", "metrics.hallucination"
            ),
            target=thresholds["smoke_hallucination_rate_max"],
        ),
        _check(
            check_id="smoke.relevance_coverage",
            source="m4_evaluation_report",
            comparator=">=",
            actual=_require_number(
                smoke_retrieval, "annotation_coverage", "metrics.retrieval"
            ),
            target=thresholds["smoke_relevance_coverage"],
        ),
        _check(
            check_id="release.query_count",
            source="retrieval_annotation_report_v2_strict_final",
            comparator=">=",
            actual=_require_number(dataset, "query_count", "dataset"),
            target=thresholds["release_query_count_min"],
        ),
        _check(
            check_id="release.total_pairs",
            source="retrieval_annotation_report_v2_strict_final",
            comparator=">=",
            actual=_require_number(dataset, "total_pairs", "dataset"),
            target=thresholds["release_total_pairs_min"],
        ),
        _check(
            check_id="release.label2_total",
            source="retrieval_annotation_report_v2_strict_final",
            comparator=">=",
            actual=label_2_count,
            target=thresholds["release_label2_count_min"],
        ),
        _check(
            check_id="release.queries_with_label2",
            source="retrieval_annotation_report_v2_strict_final",
            comparator=">=",
            actual=query_with_label_2_count,
            target=thresholds["release_queries_with_label2_min"],
        ),
        _check(
            check_id="release.min_pairs_per_query",
            source="retrieval_annotation_report_v2_strict_final",
            comparator=">=",
            actual=min_pairs_per_query,
            target=thresholds["release_min_pairs_per_query"],
        ),
    ]

    smoke_status = "PASS"
    release_status = "PASS"
    for check in checks:
        if check["id"].startswith("smoke.") and check["status"] == "FAIL":
            smoke_status = "FAIL"
        if check["id"].startswith("release.") and check["status"] == "FAIL":
            release_status = "FAIL"

    overall_status = "PASS" if smoke_status == "PASS" and release_status == "PASS" else "FAIL"

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall_status,
        "gate_status": {
            "smoke": smoke_status,
            "release": release_status,
        },
        "inputs": {
            "smoke_report_kind": "m4_evaluation_report",
            "release_report_kind": "retrieval_annotation_report_v2_strict_final",
        },
        "checks": checks,
        "summary": {
            "smoke": {
                "top10_hitrate": _require_number(
                    smoke_retrieval, "top_k_hitrate", "metrics.retrieval"
                ),
                "parsing_f1": _require_number(smoke_parsing, "f1", "metrics.parsing"),
                "hallucination_rate": _require_number(
                    smoke_hallucination, "hallucination_rate", "metrics.hallucination"
                ),
                "annotation_coverage": _require_number(
                    smoke_retrieval, "annotation_coverage", "metrics.retrieval"
                ),
            },
            "release": {
                "query_count": int(_require_number(dataset, "query_count", "dataset")),
                "total_pairs": int(_require_number(dataset, "total_pairs", "dataset")),
                "label2_total": int(label_2_count),
                "queries_with_label2": int(query_with_label_2_count),
                "min_pairs_per_query": int(min_pairs_per_query),
            },
        },
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# M4 Release Gate Report")
    lines.append("")
    lines.append(f"- generated_at_utc: {report['generated_at_utc']}")
    lines.append(f"- overall_status: {report['overall_status']}")
    lines.append(f"- smoke_gate: {report['gate_status']['smoke']}")
    lines.append(f"- release_gate: {report['gate_status']['release']}")
    lines.append("")
    lines.append("## Gate Summary")
    lines.append("")
    lines.append("| Gate | Status |")
    lines.append("| --- | :---: |")
    lines.append(f"| smoke | {report['gate_status']['smoke']} |")
    lines.append(f"| release | {report['gate_status']['release']} |")
    lines.append("")
    lines.append("## Check Details")
    lines.append("")
    lines.append("| Check | Source | Actual | Comparator | Target | Status |")
    lines.append("| --- | --- | ---: | :---: | ---: | :---: |")
    for check in report["checks"]:
        lines.append(
            f"| {check['id']} | {check['source']} | {check['actual']} | "
            f"{check['comparator']} | {check['target']} | {check['status']} |"
        )
    lines.append("")
    lines.append("## Release Readiness Interpretation")
    lines.append("")
    if report["overall_status"] == "PASS":
        lines.append("- M4 evaluation is release-ready under dual-gate policy.")
    else:
        lines.append("- M4 evaluation is not release-ready. Fix failed checks before merge.")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Check M4 smoke + release dual gates.")
    parser.add_argument(
        "--smoke-report",
        default="eval/reports/m4_evaluation_report.json",
    )
    parser.add_argument(
        "--retrieval-report",
        default="eval/reports/retrieval_annotation_report_v2_strict_final.json",
    )
    parser.add_argument(
        "--output-md",
        default="eval/reports/m4_release_report.md",
    )
    parser.add_argument(
        "--output-json",
        default="eval/reports/m4_release_report.json",
    )
    parser.add_argument("--min-smoke-top10-hitrate", type=float, default=0.70)
    parser.add_argument("--min-smoke-parsing-f1", type=float, default=0.80)
    parser.add_argument("--max-smoke-hallucination-rate", type=float, default=0.02)
    parser.add_argument("--min-smoke-relevance-coverage", type=float, default=1.0)
    parser.add_argument("--min-release-query-count", type=int, default=10)
    parser.add_argument("--min-release-total-pairs", type=int, default=1500)
    parser.add_argument("--min-release-label2-count", type=int, default=60)
    parser.add_argument("--min-release-queries-with-label2", type=int, default=6)
    parser.add_argument("--min-release-pairs-per-query", type=int, default=120)
    args = parser.parse_args()

    thresholds = {
        "smoke_top10_hitrate": float(args.min_smoke_top10_hitrate),
        "smoke_parsing_f1": float(args.min_smoke_parsing_f1),
        "smoke_hallucination_rate_max": float(args.max_smoke_hallucination_rate),
        "smoke_relevance_coverage": float(args.min_smoke_relevance_coverage),
        "release_query_count_min": float(args.min_release_query_count),
        "release_total_pairs_min": float(args.min_release_total_pairs),
        "release_label2_count_min": float(args.min_release_label2_count),
        "release_queries_with_label2_min": float(args.min_release_queries_with_label2),
        "release_min_pairs_per_query": float(args.min_release_pairs_per_query),
    }

    smoke_report = load_json(Path(args.smoke_report))
    retrieval_report = load_json(Path(args.retrieval_report))
    report = build_release_gate_report(
        smoke_report=smoke_report,
        retrieval_report=retrieval_report,
        thresholds=thresholds,
    )
    markdown = render_markdown(report)

    output_md = Path(args.output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(markdown, encoding="utf-8")

    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    dump_json(output_json, report)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["overall_status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
