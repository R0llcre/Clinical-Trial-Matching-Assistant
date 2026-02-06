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
