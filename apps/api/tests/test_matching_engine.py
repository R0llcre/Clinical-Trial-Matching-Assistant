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
    assert result["checklist"]["inclusion"][0]["rule_meta"]["field"] == "condition"
    assert result["checklist"]["exclusion"][0]["rule_meta"]["field"] == "age"


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

    exclusion = {item["rule_id"]: item for item in result["checklist"]["exclusion"]}
    assert exclusion["age"]["verdict"] == "FAIL"
    assert exclusion["sex"]["verdict"] == "UNKNOWN"
    assert exclusion["sex"]["evaluation_meta"]["missing_field"] == "demographics.sex"


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

    inclusion = {item["rule_id"]: item for item in result["checklist"]["inclusion"]}
    exclusion = {item["rule_id"]: item for item in result["checklist"]["exclusion"]}
    assert inclusion["rule-age"]["verdict"] == "PASS"
    assert inclusion["rule-sex"]["verdict"] == "PASS"
    assert exclusion["rule-exclusion"]["verdict"] == "PASS"
    assert inclusion["rule-age"]["rule_meta"]["operator"] == ">="
    assert exclusion["rule-exclusion"]["rule_meta"]["type"] == "EXCLUSION"


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


def test_evaluate_trial_lab_rule_compares_numeric_threshold() -> None:
    patient_profile = {
        "demographics": {"age": 48, "sex": "female"},
        "conditions": ["type 2 diabetes"],
        "labs": {
            "hba1c": 7.4,
            "egfr": {"value": 65, "date": "2026-01-10T00:00:00+00:00"},
        },
    }
    trial = {
        "nct_id": "NCT-LAB-1",
        "title": "A1c Target Trial",
        "conditions": ["diabetes"],
        "criteria_json": [
            {
                "id": "lab-1",
                "type": "INCLUSION",
                "field": "lab",
                "operator": ">=",
                "value": 7.0,
                "unit": "%",
                "evidence_text": "HbA1c must be at least 7.0%",
            }
        ],
    }

    result = evaluate_trial(patient_profile, trial)
    inclusion = {item["rule_id"]: item for item in result["checklist"]["inclusion"]}
    lab_rule = inclusion["lab-1"]

    assert lab_rule["rule_id"] == "lab-1"
    assert lab_rule["verdict"] == "PASS"
    assert lab_rule.get("evaluation_meta") is None


def test_evaluate_trial_within_last_history_missing_timeline_sets_required_action(
) -> None:
    patient_profile = {
        "demographics": {"age": 62, "sex": "male"},
        "conditions": ["heart failure"],
        "history": ["myocardial infarction"],
    }
    trial = {
        "nct_id": "NCT-HIST-1",
        "title": "Recent MI Exclusion Trial",
        "conditions": ["heart failure"],
        "criteria_json": [
            {
                "id": "hist-1",
                "type": "EXCLUSION",
                "field": "history",
                "operator": "WITHIN_LAST",
                "value": "myocardial infarction",
                "time_window": "6 months",
                "evidence_text": "No myocardial infarction within the last 6 months",
            }
        ],
    }

    result = evaluate_trial(patient_profile, trial)
    history_rule = result["checklist"]["exclusion"][0]

    assert history_rule["verdict"] == "UNKNOWN"
    assert history_rule["evaluation_meta"]["missing_field"] == "history_timeline"
    assert history_rule["evaluation_meta"]["reason_code"] == "MISSING_FIELD"
    assert history_rule["evaluation_meta"]["required_action"] == "ADD_HISTORY_TIMELINE"


def test_evaluate_trial_other_rule_unparsed_returns_unknown_reason_code() -> None:
    patient_profile = {
        "demographics": {"age": 54, "sex": "female"},
        "conditions": ["breast cancer"],
    }
    trial = {
        "nct_id": "NCT-OTHER-1",
        "title": "Other Criteria Trial",
        "conditions": ["breast cancer"],
        "criteria_json": [
            {
                "id": "other-1",
                "type": "EXCLUSION",
                "field": "other",
                "operator": "NOT_EXISTS",
                "value": "unparsed exclusion criteria",
                "evidence_text": "No other risk factors listed in narrative criteria",
            }
        ],
    }

    result = evaluate_trial(patient_profile, trial)
    other_rule = result["checklist"]["exclusion"][0]

    assert other_rule["verdict"] == "UNKNOWN"
    assert other_rule["evaluation_meta"]["reason_code"] == "NO_EVIDENCE"
    assert other_rule["evaluation_meta"]["required_action"] == "ADD_PROFILE_NOTES"
