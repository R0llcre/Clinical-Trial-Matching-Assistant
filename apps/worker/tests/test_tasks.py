import datetime as dt

import pytest

from tasks import _build_query_term, _extract_trial, sync_trials


def test_build_query_term_quotes_spaces() -> None:
    assert _build_query_term("breast cancer") == 'AREA[ConditionSearch]"breast cancer"'
    assert _build_query_term("diabetes") == "AREA[ConditionSearch]diabetes"


def test_extract_trial_maps_fields() -> None:
    study = {
        "protocolSection": {
            "identificationModule": {
                "nctId": "NCT123",
                "briefTitle": "Test Trial",
            },
            "statusModule": {
                "overallStatus": "RECRUITING",
                "lastUpdateSubmitDate": "2024-02-03",
            },
            "designModule": {"phases": ["PHASE2"]},
            "conditionsModule": {"conditions": ["condition-a"]},
            "eligibilityModule": {"eligibilityCriteria": "Adults only"},
            "contactsLocationsModule": {"locations": [{"country": "USA"}]},
        }
    }

    trial = _extract_trial(study)

    assert trial["nct_id"] == "NCT123"
    assert trial["title"] == "Test Trial"
    assert trial["status"] == "RECRUITING"
    assert trial["phase"] == "PHASE2"
    assert trial["conditions"] == ["condition-a"]
    assert trial["eligibility_text"] == "Adults only"
    assert trial["locations_json"] == [{"country": "USA"}]
    assert isinstance(trial["data_timestamp"], dt.datetime)


def test_sync_trials_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL not set"):
        sync_trials(condition="cancer")
