#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from validate_eval_data import validate_data_dir

QUERIES: List[Dict[str, Any]] = [
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
    {
        "query_id": "Q0003",
        "query": "heart failure trial in boston",
        "expected_conditions": ["heart failure"],
        "expected_location": {"country": "USA", "state": "MA", "city": "Boston"},
        "expected_status": None,
        "expected_phase": None,
    },
    {
        "query_id": "Q0004",
        "query": "pediatric asthma not yet recruiting",
        "expected_conditions": ["asthma"],
        "expected_location": {"country": "USA", "state": None, "city": None},
        "expected_status": "NOT_YET_RECRUITING",
        "expected_phase": None,
    },
    {
        "query_id": "Q0005",
        "query": "rheumatoid arthritis biologic trial",
        "expected_conditions": ["rheumatoid arthritis"],
        "expected_location": {"country": "USA", "state": None, "city": None},
        "expected_status": None,
        "expected_phase": "PHASE2",
    },
    {
        "query_id": "Q0006",
        "query": "advanced melanoma immunotherapy",
        "expected_conditions": ["melanoma"],
        "expected_location": {"country": "USA", "state": None, "city": None},
        "expected_status": "RECRUITING",
        "expected_phase": "PHASE2",
    },
    {
        "query_id": "Q0007",
        "query": "covid-19 long covid intervention",
        "expected_conditions": ["long covid"],
        "expected_location": {"country": "USA", "state": None, "city": None},
        "expected_status": None,
        "expected_phase": None,
    },
    {
        "query_id": "Q0008",
        "query": "chronic kidney disease phase 4",
        "expected_conditions": ["chronic kidney disease"],
        "expected_location": {"country": "USA", "state": None, "city": None},
        "expected_status": None,
        "expected_phase": "PHASE4",
    },
    {
        "query_id": "Q0009",
        "query": "ulcerative colitis study in texas",
        "expected_conditions": ["ulcerative colitis"],
        "expected_location": {"country": "USA", "state": "TX", "city": None},
        "expected_status": "RECRUITING",
        "expected_phase": None,
    },
    {
        "query_id": "Q0010",
        "query": "migraine prevention trial for women",
        "expected_conditions": ["migraine"],
        "expected_location": {"country": "USA", "state": None, "city": None},
        "expected_status": None,
        "expected_phase": "PHASE2",
    },
]

TRIALS_SAMPLE: List[Dict[str, Any]] = [
    {
        "nct_id": "NCT90000001",
        "title": "Type 2 Diabetes HbA1c Control Study",
        "eligibility_text": (
            "Inclusion: Participants must be 18 years or older. HbA1c <= 8.5%. "
            "Exclusion: Active infection or major surgery within the last 3 months."
        ),
        "labeled_rules": [
            {
                "type": "INCLUSION",
                "field": "age",
                "operator": ">=",
                "value": 18,
                "unit": "years",
                "evidence_text": "Participants must be 18 years or older.",
            },
            {
                "type": "INCLUSION",
                "field": "lab",
                "operator": "<=",
                "value": 8.5,
                "unit": "%",
                "evidence_text": "HbA1c <= 8.5%.",
            },
            {
                "type": "EXCLUSION",
                "field": "condition",
                "operator": "NOT_IN",
                "value": "active infection",
                "unit": None,
                "evidence_text": "Active infection",
            },
        ],
    },
    {
        "nct_id": "NCT90000002",
        "title": "Breast Cancer Phase 3 Combination Therapy",
        "eligibility_text": (
            "Inclusion Criteria: Female participants, 18 to 75 years. "
            "Exclusion Criteria: Pregnancy or breastfeeding."
        ),
        "labeled_rules": [
            {
                "type": "INCLUSION",
                "field": "sex",
                "operator": "=",
                "value": "female",
                "unit": None,
                "evidence_text": "Female participants",
            },
            {
                "type": "INCLUSION",
                "field": "age",
                "operator": ">=",
                "value": 18,
                "unit": "years",
                "evidence_text": "18 to 75 years",
            },
            {
                "type": "INCLUSION",
                "field": "age",
                "operator": "<=",
                "value": 75,
                "unit": "years",
                "evidence_text": "18 to 75 years",
            },
        ],
    },
    {
        "nct_id": "NCT90000003",
        "title": "Heart Failure Device Optimization",
        "eligibility_text": (
            "Inclusion: Adults with heart failure, NYHA II-III. "
            "Exclusion: Prior treatment within the last 30 days."
        ),
        "labeled_rules": [
            {
                "type": "INCLUSION",
                "field": "condition",
                "operator": "IN",
                "value": "heart failure",
                "unit": None,
                "evidence_text": "Adults with heart failure",
            },
            {
                "type": "EXCLUSION",
                "field": "medication",
                "operator": "WITHIN_LAST",
                "value": 30,
                "unit": "days",
                "evidence_text": "Prior treatment within the last 30 days.",
            },
        ],
    },
    {
        "nct_id": "NCT90000004",
        "title": "Pediatric Asthma Inhaler Trial",
        "eligibility_text": (
            "Inclusion: Age 6 to 17 years, asthma diagnosis. "
            "Exclusion: Active infection."
        ),
        "labeled_rules": [
            {
                "type": "INCLUSION",
                "field": "age",
                "operator": ">=",
                "value": 6,
                "unit": "years",
                "evidence_text": "Age 6 to 17 years",
            },
            {
                "type": "INCLUSION",
                "field": "age",
                "operator": "<=",
                "value": 17,
                "unit": "years",
                "evidence_text": "Age 6 to 17 years",
            },
            {
                "type": "INCLUSION",
                "field": "condition",
                "operator": "IN",
                "value": "asthma",
                "unit": None,
                "evidence_text": "asthma diagnosis",
            },
        ],
    },
    {
        "nct_id": "NCT90000005",
        "title": "Rheumatoid Arthritis Biologic Safety Study",
        "eligibility_text": (
            "Inclusion Criteria: Participants with rheumatoid arthritis. "
            "Exclusion Criteria: major surgery in the last 6 months."
        ),
        "labeled_rules": [
            {
                "type": "INCLUSION",
                "field": "condition",
                "operator": "IN",
                "value": "rheumatoid arthritis",
                "unit": None,
                "evidence_text": "Participants with rheumatoid arthritis.",
            },
            {
                "type": "EXCLUSION",
                "field": "procedure",
                "operator": "WITHIN_LAST",
                "value": 6,
                "unit": "months",
                "evidence_text": "major surgery in the last 6 months.",
            },
        ],
    },
    {
        "nct_id": "NCT90000006",
        "title": "Melanoma Immunotherapy Dose Expansion",
        "eligibility_text": (
            "Inclusion: Male or female participants, age >= 18. "
            "Exclusion: previous treatment in the last 4 weeks."
        ),
        "labeled_rules": [
            {
                "type": "INCLUSION",
                "field": "sex",
                "operator": "=",
                "value": "all",
                "unit": None,
                "evidence_text": "Male or female participants",
            },
            {
                "type": "INCLUSION",
                "field": "age",
                "operator": ">=",
                "value": 18,
                "unit": "years",
                "evidence_text": "age >= 18.",
            },
        ],
    },
    {
        "nct_id": "NCT90000007",
        "title": "Long COVID Rehabilitation Program",
        "eligibility_text": (
            "Inclusion Criteria: long covid symptoms for at least 3 months. "
            "Exclusion Criteria: uncontrolled psychiatric disorder."
        ),
        "labeled_rules": [
            {
                "type": "INCLUSION",
                "field": "condition",
                "operator": "IN",
                "value": "long covid",
                "unit": None,
                "evidence_text": "long covid symptoms",
            },
            {
                "type": "INCLUSION",
                "field": "other",
                "operator": "EXISTS",
                "value": None,
                "unit": None,
                "evidence_text": "for at least 3 months",
            },
        ],
    },
    {
        "nct_id": "NCT90000008",
        "title": "Migraine Prevention Trial",
        "eligibility_text": (
            "Inclusion: Adults with migraine. "
            "Exclusion: pregnancy, breastfeeding, or active infection."
        ),
        "labeled_rules": [
            {
                "type": "INCLUSION",
                "field": "condition",
                "operator": "IN",
                "value": "migraine",
                "unit": None,
                "evidence_text": "Adults with migraine.",
            },
            {
                "type": "EXCLUSION",
                "field": "history",
                "operator": "NO_HISTORY",
                "value": "pregnancy",
                "unit": None,
                "evidence_text": "pregnancy",
            },
        ],
    },
]

PATIENTS: List[Dict[str, Any]] = [
    {
        "patient_id": "P0001",
        "demographics": {"age": 52, "sex": "female"},
        "conditions": ["type 2 diabetes"],
        "medications": ["metformin"],
        "labs": [{"name": "HbA1c", "value": 7.9, "unit": "%"}],
    },
    {
        "patient_id": "P0002",
        "demographics": {"age": 61, "sex": "female"},
        "conditions": ["metastatic breast cancer"],
        "medications": ["letrozole"],
        "labs": [{"name": "ALT", "value": 29, "unit": "U/L"}],
    },
    {
        "patient_id": "P0003",
        "demographics": {"age": 69, "sex": "male"},
        "conditions": ["heart failure"],
        "medications": ["furosemide"],
        "labs": [{"name": "NT-proBNP", "value": 1500, "unit": "pg/mL"}],
    },
    {
        "patient_id": "P0004",
        "demographics": {"age": 12, "sex": "male"},
        "conditions": ["asthma"],
        "medications": ["albuterol"],
        "labs": [{"name": "FEV1", "value": 68, "unit": "%"}],
    },
    {
        "patient_id": "P0005",
        "demographics": {"age": 45, "sex": "female"},
        "conditions": ["rheumatoid arthritis"],
        "medications": ["adalimumab"],
        "labs": [{"name": "CRP", "value": 14.2, "unit": "mg/L"}],
    },
    {
        "patient_id": "P0006",
        "demographics": {"age": 58, "sex": "male"},
        "conditions": ["melanoma"],
        "medications": ["pembrolizumab"],
        "labs": [{"name": "LDH", "value": 280, "unit": "U/L"}],
    },
    {
        "patient_id": "P0007",
        "demographics": {"age": 34, "sex": "female"},
        "conditions": ["long covid"],
        "medications": [],
        "labs": [{"name": "CRP", "value": 6.4, "unit": "mg/L"}],
    },
    {
        "patient_id": "P0008",
        "demographics": {"age": 29, "sex": "female"},
        "conditions": ["migraine"],
        "medications": ["topiramate"],
        "labs": [{"name": "Creatinine", "value": 0.8, "unit": "mg/dL"}],
    },
]


def _dump_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def generate(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _dump_jsonl(output_dir / "queries.jsonl", QUERIES)
    _dump_jsonl(output_dir / "trials_sample.jsonl", TRIALS_SAMPLE)
    _dump_jsonl(output_dir / "patients.jsonl", PATIENTS)

    counts, errors = validate_data_dir(output_dir)
    if errors:
        raise ValueError(f"generated data validation failed: {errors}")
    print(json.dumps({"output_dir": str(output_dir), "counts": counts}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate reproducible M4 eval data.")
    parser.add_argument(
        "--output-dir",
        default="eval/data",
        help="Directory to write queries.jsonl/trials_sample.jsonl/patients.jsonl",
    )
    args = parser.parse_args()
    generate(Path(args.output_dir))


if __name__ == "__main__":
    main()
