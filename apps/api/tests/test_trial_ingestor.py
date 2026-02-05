import datetime as dt

import pytest
from sqlalchemy import create_engine

from app.services.trial_ingestor import extract_trial_record, upsert_trial


def test_extract_trial_record_basic() -> None:
    raw_json = {
        "protocolSection": {
            "identificationModule": {
                "nctId": "NCT123",
                "briefTitle": "Test Trial",
            },
            "statusModule": {
                "overallStatus": "RECRUITING",
                "lastUpdateSubmitDate": "2024-01-02",
            },
            "designModule": {"phases": ["PHASE2"]},
            "conditionsModule": {"conditions": ["condition-a", "condition-b"]},
            "eligibilityModule": {"eligibilityCriteria": "Adults only"},
            "contactsLocationsModule": {
                "locations": [{"city": "Boston", "country": "USA"}]
            },
        }
    }

    record = extract_trial_record(raw_json)

    assert record.nct_id == "NCT123"
    assert record.title == "Test Trial"
    assert record.status == "RECRUITING"
    assert record.phase == "PHASE2"
    assert record.conditions == ["condition-a", "condition-b"]
    assert record.eligibility_text == "Adults only"
    assert record.locations_json == [{"city": "Boston", "country": "USA"}]
    assert isinstance(record.data_timestamp, dt.datetime)
    assert record.data_timestamp.date() == dt.date(2024, 1, 2)


def test_extract_trial_record_missing_fields() -> None:
    with pytest.raises(ValueError):
        extract_trial_record({"protocolSection": {}})


def test_upsert_trial_requires_postgres() -> None:
    engine = create_engine("sqlite:///:memory:")
    record = extract_trial_record(
        {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT123",
                    "briefTitle": "Test Trial",
                }
            }
        }
    )

    with pytest.raises(RuntimeError):
        upsert_trial(engine, record)
