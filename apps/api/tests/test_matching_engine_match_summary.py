from app.services.matching_engine import evaluate_trial


def test_match_summary_eligible_with_parsed_rules() -> None:
    patient = {
        "demographics": {"age": 50, "sex": "female"},
        "conditions": ["diabetes"],
    }
    trial = {
        "nct_id": "NCT123",
        "title": "Test Trial",
        "conditions": ["diabetes"],
        "criteria_json": [
            {
                "id": "age-1",
                "type": "INCLUSION",
                "field": "age",
                "operator": ">=",
                "value": 18,
                "unit": "years",
                "evidence_text": "Age >= 18 years",
            },
            {
                "id": "sex-1",
                "type": "INCLUSION",
                "field": "sex",
                "operator": "=",
                "value": "female",
                "evidence_text": "Female participants",
            },
            {
                "id": "cond-1",
                "type": "INCLUSION",
                "field": "condition",
                "operator": "IN",
                "value": "diabetes",
                "evidence_text": "Diagnosis of diabetes",
            },
        ],
    }

    result = evaluate_trial(patient, trial)
    summary = result["match_summary"]
    assert summary["tier"] == "ELIGIBLE"
    assert summary["fail"] == 0
    assert summary["unknown"] == 0
    assert summary["missing"] == 0
    assert summary["pass"] == 3


def test_match_summary_potential_on_legacy_success_path() -> None:
    patient = {
        "demographics": {"age": 45, "sex": "female"},
        "conditions": ["diabetes"],
    }
    trial = {
        "nct_id": "NCT123",
        "title": "Legacy Trial",
        "conditions": ["type 2 diabetes mellitus"],
        "raw_json": {
            "protocolSection": {
                "eligibilityModule": {
                    "minimumAge": "18 Years",
                    "maximumAge": "65 Years",
                    "sex": "FEMALE",
                }
            }
        },
    }

    result = evaluate_trial(patient, trial)
    summary = result["match_summary"]
    assert summary["tier"] == "POTENTIAL"
    assert summary["fail"] == 0
    assert summary["unknown"] == 0
    assert summary["missing"] == 0


def test_match_summary_potential_when_missing_patient_field() -> None:
    patient = {
        "demographics": {"age": 50, "sex": "female"},
        "conditions": ["diabetes"],
    }
    trial = {
        "nct_id": "NCT123",
        "title": "Test Trial",
        "conditions": ["diabetes"],
        "criteria_json": [
            {
                "id": "hist-1",
                "type": "EXCLUSION",
                "field": "history",
                "operator": "EXISTS",
                "value": "stroke",
                "evidence_text": "History of stroke",
            }
        ],
    }

    result = evaluate_trial(patient, trial)
    summary = result["match_summary"]
    assert summary["tier"] == "POTENTIAL"
    assert summary["fail"] == 0
    assert summary["missing"] >= 1


def test_match_summary_ineligible_when_any_fail() -> None:
    patient = {
        "demographics": {"age": 50, "sex": "female"},
        "conditions": ["diabetes"],
    }
    trial = {
        "nct_id": "NCT123",
        "title": "Test Trial",
        "conditions": ["diabetes"],
        "criteria_json": [
            {
                "id": "age-1",
                "type": "INCLUSION",
                "field": "age",
                "operator": ">=",
                "value": 80,
                "unit": "years",
                "evidence_text": "Age >= 80 years",
            }
        ],
    }

    result = evaluate_trial(patient, trial)
    summary = result["match_summary"]
    assert summary["tier"] == "INELIGIBLE"
    assert summary["fail"] == 1
