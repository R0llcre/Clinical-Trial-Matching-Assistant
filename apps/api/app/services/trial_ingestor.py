from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import insert
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.engine import Engine
from sqlalchemy.schema import Column, MetaData, Table
from sqlalchemy.types import TIMESTAMP, Text

METADATA = MetaData()

TRIALS_TABLE = Table(
    "trials",
    METADATA,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("nct_id", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("conditions", ARRAY(Text)),
    Column("status", Text),
    Column("phase", Text),
    Column("eligibility_text", Text),
    Column("locations_json", JSONB),
    Column("raw_json", JSONB, nullable=False),
    Column("fetched_at", TIMESTAMP, nullable=False),
    Column("data_timestamp", TIMESTAMP, nullable=False),
    Column("source_version", Text),
    Column("created_at", TIMESTAMP, nullable=False),
    Column("updated_at", TIMESTAMP, nullable=False),
)


@dataclass
class TrialRecord:
    nct_id: str
    title: str
    status: Optional[str]
    phase: Optional[str]
    conditions: List[str]
    eligibility_text: Optional[str]
    locations_json: Optional[List[Dict[str, Any]]]
    raw_json: Dict[str, Any]
    data_timestamp: Optional[dt.datetime]


FIELD_MAP = {
    "nct_id": [("protocolSection", "identificationModule", "nctId")],
    "title": [
        ("protocolSection", "identificationModule", "briefTitle"),
        ("protocolSection", "identificationModule", "officialTitle"),
    ],
    "status": [("protocolSection", "statusModule", "overallStatus")],
    "phase": [("protocolSection", "designModule", "phases")],
    "conditions": [("protocolSection", "conditionsModule", "conditions")],
    "eligibility_text": [
        ("protocolSection", "eligibilityModule", "eligibilityCriteria")
    ],
    "locations_json": [
        ("protocolSection", "contactsLocationsModule", "locations")
    ],
}

DATE_CANDIDATES = [
    ("protocolSection", "statusModule", "lastUpdateSubmitDate"),
    ("protocolSection", "statusModule", "lastUpdatePostDateStruct", "date"),
    ("protocolSection", "statusModule", "studyFirstPostDateStruct", "date"),
]


def _get_value(raw_json: Dict[str, Any], path: Sequence[str]) -> Any:
    cursor: Any = raw_json
    for key in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    return cursor


def _get_first(raw_json: Dict[str, Any], paths: Iterable[Sequence[str]]) -> Any:
    for path in paths:
        value = _get_value(raw_json, path)
        if value is not None:
            return value
    return None


def _parse_timestamp(value: Optional[str]) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def extract_trial_record(raw_json: Dict[str, Any]) -> TrialRecord:
    """Extract structured fields from a CT.gov raw study JSON payload."""
    nct_id = _get_first(raw_json, FIELD_MAP["nct_id"])
    title = _get_first(raw_json, FIELD_MAP["title"])
    status = _get_first(raw_json, FIELD_MAP["status"])
    phase_value = _get_first(raw_json, FIELD_MAP["phase"])
    conditions = _get_first(raw_json, FIELD_MAP["conditions"]) or []
    eligibility_text = _get_first(raw_json, FIELD_MAP["eligibility_text"])
    locations_json = _get_first(raw_json, FIELD_MAP["locations_json"])

    if not nct_id or not title:
        raise ValueError("Missing required fields in trial record")

    phase = None
    if isinstance(phase_value, list) and phase_value:
        phase = phase_value[0]
    elif isinstance(phase_value, str):
        phase = phase_value

    data_timestamp = None
    for path in DATE_CANDIDATES:
        data_timestamp = _parse_timestamp(_get_value(raw_json, path))
        if data_timestamp:
            break

    if not isinstance(conditions, list):
        conditions = [str(conditions)]

    return TrialRecord(
        nct_id=str(nct_id),
        title=str(title),
        status=status,
        phase=phase,
        conditions=conditions,
        eligibility_text=eligibility_text,
        locations_json=locations_json,
        raw_json=raw_json,
        data_timestamp=data_timestamp,
    )


def upsert_trial(engine: Engine, record: TrialRecord) -> None:
    """Insert or update a trial record keyed by nct_id."""
    if engine.dialect.name != "postgresql":
        raise RuntimeError("trial_ingestor currently supports PostgreSQL only")

    now = dt.datetime.utcnow()
    payload = {
        "nct_id": record.nct_id,
        "title": record.title,
        "status": record.status,
        "phase": record.phase,
        "conditions": record.conditions,
        "eligibility_text": record.eligibility_text,
        "locations_json": record.locations_json,
        "raw_json": record.raw_json,
        "data_timestamp": record.data_timestamp or now,
    }

    stmt = (
        insert(TRIALS_TABLE)
        .values(
            id=str(uuid.uuid4()),
            fetched_at=now,
            created_at=now,
            updated_at=now,
            source_version="ctgov-v2",
            **payload,
        )
        .on_conflict_do_update(
            index_elements=[TRIALS_TABLE.c.nct_id],
            set_={
                **payload,
                "fetched_at": now,
                "updated_at": now,
                "source_version": "ctgov-v2",
            },
        )
    )

    with engine.begin() as conn:
        conn.execute(stmt)
