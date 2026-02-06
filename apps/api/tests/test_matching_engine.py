from app.services.matching_engine import evaluate_trial


def test_evaluate_trial_pass_path() -> None:
    patient_profile = {
        "demographics": {"age": 45, "sex": "female"},
        "conditions": ["type 2 diabetes"],
    }
    trial = {
        "nct_id": "NCT-1",
        "title": "Diabetes Trial",
        "status": "RECRUITING",
        "phase": "PHASE2",
        "conditions": ["diabetes mellitus"],
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

    result = evaluate_trial(patient_profile, trial)

    assert result["nct_id"] == "NCT-1"
    assert result["score"] > 0
    assert result["certainty"] > 0
    assert result["checklist"]["missing_info"] == []
    assert result["checklist"]["inclusion"][0]["verdict"] == "PASS"

    exclusion = {
        item["rule_id"]: item["verdict"] for item in result["checklist"]["exclusion"]
    }
    assert exclusion["age"] == "PASS"
    assert exclusion["sex"] == "PASS"


def test_evaluate_trial_fail_and_unknown_path() -> None:
    patient_profile = {
        "demographics": {"age": 70},
    }
    trial = {
        "nct_id": "NCT-2",
        "title": "Hypertension Trial",
        "conditions": ["hypertension"],
        "raw_json": {
            "protocolSection": {
                "eligibilityModule": {
                    "minimumAge": "18 Years",
                    "maximumAge": "65 Years",
                    "sex": "MALE",
                }
            }
        },
    }

    result = evaluate_trial(patient_profile, trial)

    assert result["score"] < -50
    assert "conditions" in result["checklist"]["missing_info"]
    assert "demographics.sex" in result["checklist"]["missing_info"]
    assert result["checklist"]["inclusion"][0]["verdict"] == "UNKNOWN"

    exclusion = {
        item["rule_id"]: item["verdict"] for item in result["checklist"]["exclusion"]
    }
    assert exclusion["age"] == "FAIL"
    assert exclusion["sex"] == "UNKNOWN"


def test_evaluate_trial_prefers_parsed_criteria_rules() -> None:
    patient_profile = {
        "demographics": {"age": 34, "sex": "female"},
        "conditions": ["diabetes mellitus type 2"],
    }
    trial = {
        "nct_id": "NCT-3",
        "title": "Parsed Criteria Trial",
        "status": "RECRUITING",
        "phase": "PHASE2",
        "fetched_at": "2026-02-10T00:00:00",
        "criteria_json": [
            {
                "id": "rule-age",
                "type": "INCLUSION",
                "field": "age",
                "operator": ">=",
                "value": 18,
                "unit": "years",
                "evidence_text": "Participants must be at least 18 years old.",
            },
            {
                "id": "rule-sex",
                "type": "INCLUSION",
                "field": "sex",
                "operator": "=",
                "value": "female",
                "evidence_text": "Female participants only.",
            },
            {
                "id": "rule-exclusion",
                "type": "EXCLUSION",
                "field": "condition",
                "operator": "NOT_IN",
                "value": "active infection",
                "evidence_text": "No active infection.",
            },
        ],
        "raw_json": {},
    }

    result = evaluate_trial(patient_profile, trial)

    assert result["score"] > 0
    assert result["checklist"]["missing_info"] == []

    inclusion = {
        item["rule_id"]: item["verdict"] for item in result["checklist"]["inclusion"]
    }
    exclusion = {
        item["rule_id"]: item["verdict"] for item in result["checklist"]["exclusion"]
    }
    assert inclusion["rule-age"] == "PASS"
    assert inclusion["rule-sex"] == "PASS"
    assert exclusion["rule-exclusion"] == "PASS"


def test_evaluate_trial_with_parsed_rules_keeps_condition_overlap() -> None:
    patient_profile = {
        "demographics": {"age": 34, "sex": "female"},
        "conditions": ["diabetes mellitus"],
    }
    trial = {
        "nct_id": "NCT-4",
        "title": "Unrelated Cancer Trial",
        "status": "RECRUITING",
        "phase": "PHASE2",
        "conditions": ["metastatic breast cancer"],
        "criteria_json": [
            {
                "id": "rule-age",
                "type": "INCLUSION",
                "field": "age",
                "operator": ">=",
                "value": 18,
                "unit": "years",
                "evidence_text": "Participants must be at least 18 years old.",
            },
            {
                "id": "rule-sex",
                "type": "INCLUSION",
                "field": "sex",
                "operator": "=",
                "value": "female",
                "evidence_text": "Female participants only.",
            },
        ],
        "raw_json": {},
    }

    result = evaluate_trial(patient_profile, trial)

    inclusion = {
        item["rule_id"]: item["verdict"] for item in result["checklist"]["inclusion"]
    }
    assert inclusion["condition_match"] == "FAIL"
    assert inclusion["rule-age"] == "PASS"
    assert inclusion["rule-sex"] == "PASS"
