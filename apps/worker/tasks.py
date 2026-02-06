from __future__ import annotations

import datetime as dt
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

import httpx
import psycopg
from psycopg.types.json import Json

from services.eligibility_parser import parse_criteria_v1

DEFAULT_BASE_URL = "https://clinicaltrials.gov/api/v2"
LOGGER = logging.getLogger(__name__)


@dataclass
class SyncStats:
    run_id: str
    condition: str
    status: Optional[str]
    pages: int
    processed: int
    inserted: int
    updated: int


@dataclass
class ParseStats:
    run_id: str
    nct_id: str
    parser_version: str
    status: str
    rule_count: int
    unknown_count: int


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
    "locations_json": [("protocolSection", "contactsLocationsModule", "locations")],
}

DATE_CANDIDATES = [
    ("protocolSection", "statusModule", "lastUpdateSubmitDate"),
    ("protocolSection", "statusModule", "lastUpdatePostDateStruct", "date"),
    ("protocolSection", "statusModule", "studyFirstPostDateStruct", "date"),
]


class CTGovClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
    ) -> None:
        base = base_url or os.getenv("CTGOV_BASE_URL") or DEFAULT_BASE_URL
        self.base_url = base.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    def search_studies(
        self,
        condition: str,
        status: Optional[str] = None,
        page_token: Optional[str] = None,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        params: Dict[str, str] = {
            "query.term": _build_query_term(condition),
            "pageSize": str(page_size),
        }
        if status:
            params["filter.overallStatus"] = status
        if page_token:
            params["pageToken"] = page_token
        return self._request_json("/studies", params)

    def _request_json(self, path: str, params: Dict[str, str]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.get(url, params=params)
                    if response.status_code >= 500 or response.status_code == 429:
                        raise httpx.HTTPStatusError(
                            f"server error {response.status_code}",
                            request=response.request,
                            response=response,
                        )
                    response.raise_for_status()
                    return response.json()
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt == self.max_retries - 1:
                    break
                time.sleep(self.backoff_seconds * (2**attempt))

        raise RuntimeError(f"CTGov request failed: {last_error}") from last_error


def _build_query_term(condition: str) -> str:
    term = condition.strip()
    if " " in term:
        term = f'"{term}"'
    return f"AREA[ConditionSearch]{term}"


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


def _extract_trial(study: Dict[str, Any]) -> Dict[str, Any]:
    nct_id = _get_first(study, FIELD_MAP["nct_id"])
    title = _get_first(study, FIELD_MAP["title"])
    if not nct_id or not title:
        raise ValueError("Missing required trial fields")

    phase_value = _get_first(study, FIELD_MAP["phase"])
    phase = None
    if isinstance(phase_value, list) and phase_value:
        phase = phase_value[0]
    elif isinstance(phase_value, str):
        phase = phase_value

    conditions = _get_first(study, FIELD_MAP["conditions"]) or []
    if not isinstance(conditions, list):
        conditions = [str(conditions)]

    data_timestamp = None
    for path in DATE_CANDIDATES:
        data_timestamp = _parse_timestamp(_get_value(study, path))
        if data_timestamp:
            break

    return {
        "nct_id": str(nct_id),
        "title": str(title),
        "status": _get_first(study, FIELD_MAP["status"]),
        "phase": phase,
        "conditions": conditions,
        "eligibility_text": _get_first(study, FIELD_MAP["eligibility_text"]),
        "locations_json": _get_first(study, FIELD_MAP["locations_json"]),
        "raw_json": study,
        "data_timestamp": data_timestamp,
    }


def _ensure_tables(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS trials (
              id UUID PRIMARY KEY,
              nct_id TEXT UNIQUE NOT NULL,
              title TEXT NOT NULL,
              conditions TEXT[],
              status TEXT,
              phase TEXT,
              eligibility_text TEXT,
              locations_json JSONB,
              raw_json JSONB NOT NULL,
              fetched_at TIMESTAMP NOT NULL,
              data_timestamp TIMESTAMP NOT NULL,
              source_version TEXT,
              created_at TIMESTAMP NOT NULL,
              updated_at TIMESTAMP NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_logs (
              id UUID PRIMARY KEY,
              run_id UUID NOT NULL,
              task_name TEXT NOT NULL,
              status TEXT NOT NULL,
              condition TEXT,
              trial_status TEXT,
              pages INTEGER NOT NULL,
              processed INTEGER NOT NULL,
              inserted INTEGER NOT NULL,
              updated INTEGER NOT NULL,
              error_message TEXT,
              created_at TIMESTAMP NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS trial_criteria (
              id UUID PRIMARY KEY,
              trial_id UUID NOT NULL REFERENCES trials(id),
              parser_version TEXT NOT NULL,
              criteria_json JSONB NOT NULL,
              coverage_stats JSONB,
              created_at TIMESTAMP NOT NULL,
              UNIQUE (trial_id, parser_version)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS parse_logs (
              id UUID PRIMARY KEY,
              run_id UUID NOT NULL,
              task_name TEXT NOT NULL,
              nct_id TEXT NOT NULL,
              parser_version TEXT NOT NULL,
              status TEXT NOT NULL,
              error_message TEXT,
              created_at TIMESTAMP NOT NULL
            )
            """
        )


def _upsert_trial(conn: psycopg.Connection, trial: Dict[str, Any]) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM trials WHERE nct_id = %s", (trial["nct_id"],))
        exists = cur.fetchone() is not None

        now = dt.datetime.utcnow()
        data_timestamp = trial["data_timestamp"] or now
        cur.execute(
            """
            INSERT INTO trials (
              id, nct_id, title, conditions, status, phase, eligibility_text,
              locations_json, raw_json, fetched_at, data_timestamp,
              source_version, created_at, updated_at
            ) VALUES (
              %(id)s, %(nct_id)s, %(title)s, %(conditions)s, %(status)s, %(phase)s,
              %(eligibility_text)s, %(locations_json)s, %(raw_json)s, %(fetched_at)s,
              %(data_timestamp)s, %(source_version)s, %(created_at)s, %(updated_at)s
            )
            ON CONFLICT (nct_id) DO UPDATE SET
              title = EXCLUDED.title,
              conditions = EXCLUDED.conditions,
              status = EXCLUDED.status,
              phase = EXCLUDED.phase,
              eligibility_text = EXCLUDED.eligibility_text,
              locations_json = EXCLUDED.locations_json,
              raw_json = EXCLUDED.raw_json,
              fetched_at = EXCLUDED.fetched_at,
              data_timestamp = EXCLUDED.data_timestamp,
              source_version = EXCLUDED.source_version,
              updated_at = EXCLUDED.updated_at
            """,
            {
                "id": str(uuid.uuid4()),
                "nct_id": trial["nct_id"],
                "title": trial["title"],
                "conditions": trial["conditions"],
                "status": trial["status"],
                "phase": trial["phase"],
                "eligibility_text": trial["eligibility_text"],
                "locations_json": Json(trial["locations_json"]),
                "raw_json": Json(trial["raw_json"]),
                "fetched_at": now,
                "data_timestamp": data_timestamp,
                "source_version": "ctgov-v2",
                "created_at": now,
                "updated_at": now,
            },
        )

    return not exists


def _write_sync_log(
    conn: psycopg.Connection,
    *,
    run_id: str,
    status: str,
    condition: str,
    trial_status: Optional[str],
    pages: int,
    processed: int,
    inserted: int,
    updated: int,
    error_message: Optional[str],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sync_logs (
              id, run_id, task_name, status, condition, trial_status,
              pages, processed, inserted, updated, error_message, created_at
            ) VALUES (
              %(id)s, %(run_id)s, %(task_name)s, %(status)s, %(condition)s,
              %(trial_status)s, %(pages)s, %(processed)s, %(inserted)s,
              %(updated)s, %(error_message)s, %(created_at)s
            )
            """,
            {
                "id": str(uuid.uuid4()),
                "run_id": run_id,
                "task_name": "sync_trials",
                "status": status,
                "condition": condition,
                "trial_status": trial_status,
                "pages": pages,
                "processed": processed,
                "inserted": inserted,
                "updated": updated,
                "error_message": error_message,
                "created_at": dt.datetime.utcnow(),
            },
        )


def _fetch_trial_for_parse(
    conn: psycopg.Connection, nct_id: str
) -> Optional[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, nct_id, eligibility_text
            FROM trials
            WHERE nct_id = %s
            LIMIT 1
            """,
            (nct_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]),
        "nct_id": str(row[1]),
        "eligibility_text": row[2],
    }


def _upsert_trial_criteria(
    conn: psycopg.Connection,
    *,
    trial_id: str,
    parser_version: str,
    criteria_json: List[Dict[str, Any]],
    coverage_stats: Dict[str, Any],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trial_criteria (
              id, trial_id, parser_version, criteria_json, coverage_stats, created_at
            ) VALUES (
              %(id)s, %(trial_id)s, %(parser_version)s,
              %(criteria_json)s, %(coverage_stats)s, %(created_at)s
            )
            ON CONFLICT (trial_id, parser_version) DO UPDATE SET
              criteria_json = EXCLUDED.criteria_json,
              coverage_stats = EXCLUDED.coverage_stats,
              created_at = EXCLUDED.created_at
            """,
            {
                "id": str(uuid.uuid4()),
                "trial_id": trial_id,
                "parser_version": parser_version,
                "criteria_json": Json(criteria_json),
                "coverage_stats": Json(coverage_stats),
                "created_at": dt.datetime.utcnow(),
            },
        )


def _write_parse_log(
    conn: psycopg.Connection,
    *,
    run_id: str,
    nct_id: str,
    parser_version: str,
    status: str,
    error_message: Optional[str],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO parse_logs (
              id, run_id, task_name, nct_id, parser_version,
              status, error_message, created_at
            ) VALUES (
              %(id)s, %(run_id)s, %(task_name)s, %(nct_id)s,
              %(parser_version)s, %(status)s, %(error_message)s, %(created_at)s
            )
            """,
            {
                "id": str(uuid.uuid4()),
                "run_id": run_id,
                "task_name": "parse_trial",
                "nct_id": nct_id,
                "parser_version": parser_version,
                "status": status,
                "error_message": error_message,
                "created_at": dt.datetime.utcnow(),
            },
        )


def sync_trials(
    condition: str,
    status: Optional[str] = None,
    *,
    page_limit: int = 1,
    page_size: int = 100,
) -> SyncStats:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL not set")

    run_id = str(uuid.uuid4())
    client = CTGovClient()

    pages = 0
    processed = 0
    inserted = 0
    updated = 0

    LOGGER.info(
        "sync_trials started run_id=%s condition=%s status=%s",
        run_id,
        condition,
        status,
    )

    with psycopg.connect(database_url) as conn:
        _ensure_tables(conn)
        conn.commit()

        try:
            next_page_token: Optional[str] = None
            while pages < page_limit:
                page = client.search_studies(
                    condition=condition,
                    status=status,
                    page_token=next_page_token,
                    page_size=page_size,
                )
                pages += 1

                studies = page.get("studies") or []
                if not studies:
                    break

                for study in studies:
                    trial = _extract_trial(study)
                    is_insert = _upsert_trial(conn, trial)
                    processed += 1
                    if is_insert:
                        inserted += 1
                    else:
                        updated += 1

                next_page_token = page.get("nextPageToken")
                if not next_page_token:
                    break

            _write_sync_log(
                conn,
                run_id=run_id,
                status="SUCCESS",
                condition=condition,
                trial_status=status,
                pages=pages,
                processed=processed,
                inserted=inserted,
                updated=updated,
                error_message=None,
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            _ensure_tables(conn)
            _write_sync_log(
                conn,
                run_id=run_id,
                status="FAILED",
                condition=condition,
                trial_status=status,
                pages=pages,
                processed=processed,
                inserted=inserted,
                updated=updated,
                error_message=str(exc),
            )
            conn.commit()
            LOGGER.exception(
                "sync_trials failed run_id=%s condition=%s status=%s",
                run_id,
                condition,
                status,
            )
            raise

    stats = SyncStats(
        run_id=run_id,
        condition=condition,
        status=status,
        pages=pages,
        processed=processed,
        inserted=inserted,
        updated=updated,
    )
    LOGGER.info(
        "sync_trials completed run_id=%s pages=%s processed=%s inserted=%s updated=%s",
        run_id,
        pages,
        processed,
        inserted,
        updated,
    )
    return stats


def parse_trial(
    nct_id: str,
    parser_version: str = "rule_v1",
) -> ParseStats:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL not set")

    run_id = str(uuid.uuid4())

    LOGGER.info(
        "parse_trial started run_id=%s nct_id=%s parser_version=%s",
        run_id,
        nct_id,
        parser_version,
    )

    with psycopg.connect(database_url) as conn:
        _ensure_tables(conn)
        conn.commit()

        try:
            trial = _fetch_trial_for_parse(conn, nct_id)
            if not trial:
                raise ValueError(f"trial not found: {nct_id}")

            if parser_version != "rule_v1":
                raise ValueError(f"unsupported parser_version: {parser_version}")

            criteria_json = parse_criteria_v1(trial.get("eligibility_text"))
            unknown_count = sum(
                1
                for rule in criteria_json
                if rule.get("field") == "other" and rule.get("certainty") == "low"
            )
            coverage_stats = {
                "total_rules": len(criteria_json),
                "unknown_rules": unknown_count,
                "known_rules": len(criteria_json) - unknown_count,
            }

            _upsert_trial_criteria(
                conn,
                trial_id=trial["id"],
                parser_version=parser_version,
                criteria_json=criteria_json,
                coverage_stats=coverage_stats,
            )
            _write_parse_log(
                conn,
                run_id=run_id,
                nct_id=nct_id,
                parser_version=parser_version,
                status="SUCCESS",
                error_message=None,
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            _ensure_tables(conn)
            _write_parse_log(
                conn,
                run_id=run_id,
                nct_id=nct_id,
                parser_version=parser_version,
                status="FAILED",
                error_message=str(exc),
            )
            conn.commit()
            LOGGER.exception(
                "parse_trial failed run_id=%s nct_id=%s parser_version=%s",
                run_id,
                nct_id,
                parser_version,
            )
            raise

    stats = ParseStats(
        run_id=run_id,
        nct_id=nct_id,
        parser_version=parser_version,
        status="SUCCESS",
        rule_count=len(criteria_json),
        unknown_count=unknown_count,
    )
    LOGGER.info(
        "parse_trial completed run_id=%s nct_id=%s parser_version=%s rules=%s unknown=%s",
        run_id,
        nct_id,
        parser_version,
        stats.rule_count,
        stats.unknown_count,
    )
    return stats
