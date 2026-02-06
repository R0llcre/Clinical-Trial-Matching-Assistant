from __future__ import annotations

import zipfile
from pathlib import Path

from generate_retrieval_v2_tasks_aact import build_candidates_from_aact_zip


def _write_member(zipf: zipfile.ZipFile, name: str, lines: list[str]) -> None:
    zipf.writestr(name, "".join(lines))


def test_build_candidates_from_aact_zip_matches_conditions_and_adds_background(
    tmp_path: Path,
) -> None:
    zip_path = tmp_path / "mini_aact.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        _write_member(
            zipf,
            "conditions.txt",
            [
                "id|nct_id|name|downcase_name\n",
                "1|NCT1|Type 2 Diabetes|type 2 diabetes\n",
                "2|NCT2|Metastatic Breast Cancer|metastatic breast cancer\n",
                "3|NCT3|Heart Failure|heart failure\n",
            ],
        )
        _write_member(
            zipf,
            "studies.txt",
            [
                "nct_id|brief_title|overall_status|phase\n",
                "NCT1|Diabetes trial|RECRUITING|PHASE2\n",
                "NCT2|Breast trial|RECRUITING|PHASE3\n",
                "NCT3|HF trial|COMPLETED|PHASE2\n",
            ],
        )
        _write_member(
            zipf,
            "facilities.txt",
            [
                "id|nct_id|status|name|city|state|zip|country|latitude|longitude\n",
                "1|NCT1|ACTIVE|A|San Diego|CA|00000|USA||\n",
                "2|NCT2|ACTIVE|B|Boston|MA|00000|USA||\n",
                "3|NCT3|ACTIVE|C|Austin|TX|00000|USA||\n",
            ],
        )

    queries = [
        {
            "query_id": "Q0001",
            "query": "type 2 diabetes recruiting phase 2 in california",
            "expected_conditions": ["type 2 diabetes"],
            "expected_location": {"country": "USA", "state": "CA", "city": None},
            "expected_status": "RECRUITING",
            "expected_phase": "PHASE2",
        },
        {
            "query_id": "Q0002",
            "query": "metastatic breast cancer phase 3",
            "expected_conditions": ["metastatic breast cancer"],
            "expected_location": {"country": "USA", "state": None, "city": None},
            "expected_status": "RECRUITING",
            "expected_phase": "PHASE3",
        },
    ]

    candidates_by_query, summary = build_candidates_from_aact_zip(
        zip_path=zip_path,
        queries=queries,
        max_candidates_per_query=3,
        background_per_query=1,
    )

    assert summary["global_positive_ncts"] == 2
    assert len(candidates_by_query["Q0001"]) == 2
    assert len(candidates_by_query["Q0002"]) == 2
    q1_ncts = {item["nct_id"] for item in candidates_by_query["Q0001"]}
    q2_ncts = {item["nct_id"] for item in candidates_by_query["Q0002"]}
    assert "NCT1" in q1_ncts
    assert "NCT2" in q2_ncts
    # Cross-query background should be present.
    assert "NCT2" in q1_ncts
    assert "NCT1" in q2_ncts
