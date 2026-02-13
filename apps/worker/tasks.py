from __future__ import annotations

import datetime as dt
import logging
import os
import time
import uuid
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Dict, Iterable, List, Optional, Sequence

import httpx
import psycopg
from psycopg.types.json import Json

from services.eligibility_parser import parse_criteria_v1
from services.llm_eligibility_parser import parse_criteria_llm_v1_with_fallback

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
    parse_success: int
    parse_failed: int
    parse_success_rate: float
    pruned_trials: int = 0
    pruned_criteria: int = 0
    parser_version: str = "rule_v1"
    parser_source_breakdown: Dict[str, int] = dataclass_field(default_factory=dict)
    fallback_reason_breakdown: Dict[str, int] = dataclass_field(default_factory=dict)
    llm_budget_exceeded_count: int = 0
    backfill_selected: int = 0
    selective_llm_triggered: int = 0
    selective_llm_skipped_breakdown: Dict[str, int] = dataclass_field(
        default_factory=dict
    )


@dataclass
class ParseStats:
    run_id: str
    nct_id: str
    parser_version: str
    status: str
    rule_count: int
    unknown_count: int
    parser_source: str = "rule_v1"
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    llm_budget_exceeded: bool = False


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
        params: Dict[str, str] = {"pageSize": str(page_size)}
        if not _is_global_condition(condition):
            params["query.term"] = _build_query_term(condition)
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


def _is_global_condition(condition: str) -> bool:
    normalized = condition.strip().lower()
    return normalized in {"__all__", "all", "*", ""}


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
            CREATE TABLE IF NOT EXISTS sync_cursors (
              condition TEXT NOT NULL,
              trial_status TEXT NOT NULL,
              next_page_token TEXT,
              updated_at TIMESTAMP NOT NULL,
              PRIMARY KEY (condition, trial_status)
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
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_usage_logs (
              id UUID PRIMARY KEY,
              run_id UUID NOT NULL,
              nct_id TEXT NOT NULL,
              parser_version TEXT NOT NULL,
              prompt_tokens INTEGER,
              completion_tokens INTEGER,
              total_tokens INTEGER NOT NULL,
              usage_date DATE NOT NULL,
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


def _cursor_key_status(status: Optional[str]) -> str:
    return (status or "").strip()


def _read_sync_cursor(
    conn: psycopg.Connection, *, condition: str, trial_status: str
) -> Optional[str]:
    condition = condition.strip()
    trial_status = trial_status.strip()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT next_page_token
            FROM sync_cursors
            WHERE condition = %s AND trial_status = %s
            """,
            (condition, trial_status),
        )
        row = cur.fetchone()
    if not row or not row[0]:
        return None
    return str(row[0])


def _write_sync_cursor(
    conn: psycopg.Connection,
    *,
    condition: str,
    trial_status: str,
    next_page_token: Optional[str],
) -> None:
    condition = condition.strip()
    trial_status = trial_status.strip()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sync_cursors (
              condition, trial_status, next_page_token, updated_at
            ) VALUES (
              %(condition)s, %(trial_status)s, %(next_page_token)s, %(updated_at)s
            )
            ON CONFLICT (condition, trial_status) DO UPDATE SET
              next_page_token = EXCLUDED.next_page_token,
              updated_at = EXCLUDED.updated_at
            """,
            {
                "condition": condition,
                "trial_status": trial_status,
                "next_page_token": next_page_token,
                "updated_at": dt.datetime.utcnow(),
            },
        )


def _trial_total(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM trials")
        row = cur.fetchone()
    if not row:
        return 0
    return int(row[0] or 0)


def _prune_trials_to_status_filter(
    conn: psycopg.Connection, *, allowed_statuses: list[str]
) -> tuple[int, int]:
    allowed_statuses = [status.strip() for status in allowed_statuses if status.strip()]
    if not allowed_statuses:
        return 0, 0

    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM trial_criteria AS tc
            USING trials AS t
            WHERE tc.trial_id = t.id
              AND (t.status IS NULL OR NOT (t.status = ANY(%(allowed_statuses)s)))
            """,
            {"allowed_statuses": allowed_statuses},
        )
        deleted_criteria = int(cur.rowcount or 0)

        cur.execute(
            """
            DELETE FROM trials AS t
            WHERE (t.status IS NULL OR NOT (t.status = ANY(%(allowed_statuses)s)))
            """,
            {"allowed_statuses": allowed_statuses},
        )
        deleted_trials = int(cur.rowcount or 0)

    return deleted_criteria, deleted_trials


def _recent_llm_usage_nct_ids(
    conn: psycopg.Connection,
    *,
    nct_ids: Sequence[str],
    within_hours: int,
) -> set[str]:
    if not nct_ids:
        return set()
    within_hours = max(1, int(within_hours))
    unique = sorted({str(item) for item in nct_ids if str(item).strip()})
    if not unique:
        return set()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT nct_id
            FROM llm_usage_logs
            WHERE nct_id = ANY(%s)
              AND created_at >= NOW() - make_interval(hours => %s)
            """,
            (unique, within_hours),
        )
        rows = cur.fetchall()
    return {str(row[0]) for row in rows if row and row[0]}


def _should_trigger_selective_llm(
    stats: ParseStats,
    *,
    unknown_ratio_threshold: float,
    unknown_rules_min: int,
) -> bool:
    rule_count = max(0, int(getattr(stats, "rule_count", 0)))
    unknown_count = max(0, int(getattr(stats, "unknown_count", 0)))
    if rule_count <= 0:
        return False
    if rule_count <= 2 and unknown_count >= 1:
        return True
    unknown_ratio = float(unknown_count) / float(max(rule_count, 1))
    return unknown_count >= max(1, int(unknown_rules_min)) and unknown_ratio >= float(
        unknown_ratio_threshold
    )


def _select_backfill_nct_ids(
    conn: psycopg.Connection,
    *,
    limit: int,
    coverage_ratio_threshold: float,
    cooldown_hours: int,
) -> List[str]:
    limit = max(0, int(limit))
    if limit <= 0:
        return []
    coverage_ratio_threshold = float(coverage_ratio_threshold)
    cooldown_hours = max(1, int(cooldown_hours))

    selected: List[str] = []
    seen: set[str] = set()

    # 1) Trials without any criteria rows.
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.nct_id
            FROM trials AS t
            WHERE t.eligibility_text IS NOT NULL
              AND btrim(t.eligibility_text) <> ''
              AND NOT EXISTS (
                SELECT 1 FROM trial_criteria AS tc
                WHERE tc.trial_id = t.id
              )
              AND NOT EXISTS (
                SELECT 1 FROM llm_usage_logs AS l
                WHERE l.nct_id = t.nct_id
                  AND l.created_at >= NOW() - make_interval(hours => %s)
              )
            ORDER BY t.fetched_at DESC
            LIMIT %s
            """,
            (cooldown_hours, limit),
        )
        rows = cur.fetchall()
    for row in rows:
        nct_id = str(row[0]) if row and row[0] else ""
        if not nct_id or nct_id in seen:
            continue
        selected.append(nct_id)
        seen.add(nct_id)
        if len(selected) >= limit:
            return selected

    remaining = limit - len(selected)
    if remaining <= 0:
        return selected

    # 2) Trials with low coverage latest criteria from rule_v1, excluding successful llm.
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH latest AS (
              SELECT DISTINCT ON (trial_id)
                trial_id,
                parser_version,
                coverage_stats,
                created_at
              FROM trial_criteria
              ORDER BY trial_id, created_at DESC
            )
            SELECT t.nct_id
            FROM trials AS t
            JOIN latest AS lc
              ON lc.trial_id = t.id
            WHERE t.eligibility_text IS NOT NULL
              AND btrim(t.eligibility_text) <> ''
              AND COALESCE(NULLIF(lc.coverage_stats->>'parser_source', ''), lc.parser_version, '') = 'rule_v1'
              AND COALESCE((lc.coverage_stats->>'coverage_ratio')::float, 1.0) < %s
              AND NOT EXISTS (
                SELECT 1
                FROM trial_criteria AS tc2
                WHERE tc2.trial_id = t.id
                  AND tc2.parser_version = 'llm_v1'
                  AND COALESCE(NULLIF(tc2.coverage_stats->>'parser_source', ''), '') = 'llm_v1'
              )
              AND NOT EXISTS (
                SELECT 1 FROM llm_usage_logs AS l
                WHERE l.nct_id = t.nct_id
                  AND l.created_at >= NOW() - make_interval(hours => %s)
              )
            ORDER BY t.fetched_at DESC
            LIMIT %s
            """,
            (coverage_ratio_threshold, cooldown_hours, remaining),
        )
        rows = cur.fetchall()
    for row in rows:
        nct_id = str(row[0]) if row and row[0] else ""
        if not nct_id or nct_id in seen:
            continue
        selected.append(nct_id)
        seen.add(nct_id)
        if len(selected) >= limit:
            break

    return selected


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


def _read_llm_daily_token_budget() -> int:
    raw = os.getenv("LLM_DAILY_TOKEN_BUDGET", "200000")
    try:
        return int(raw)
    except ValueError:
        return 200000


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _default_sync_parser_version() -> str:
    explicit = str(os.getenv("SYNC_PARSER_VERSION", "")).strip().lower()
    if explicit in {"rule_v1", "llm_v1"}:
        return explicit
    return "llm_v1" if _env_bool("LLM_PARSER_ENABLED", False) else "rule_v1"


def _daily_llm_token_usage(conn: psycopg.Connection, usage_date: dt.date) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(total_tokens), 0)
            FROM llm_usage_logs
            WHERE usage_date = %s
            """,
            (usage_date,),
        )
        row = cur.fetchone()
    if not row:
        return 0
    return int(row[0] or 0)


def _is_llm_budget_exceeded(conn: psycopg.Connection, usage_date: dt.date) -> bool:
    budget = _read_llm_daily_token_budget()
    if budget <= 0:
        return True
    used_tokens = _daily_llm_token_usage(conn, usage_date)
    return used_tokens >= budget


def _write_llm_usage_log(
    conn: psycopg.Connection,
    *,
    run_id: str,
    nct_id: str,
    parser_version: str,
    usage: Dict[str, Any],
) -> None:
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")
    if isinstance(total_tokens, int):
        total = total_tokens
    else:
        total = 0
    now = dt.datetime.now(dt.UTC)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO llm_usage_logs (
              id, run_id, nct_id, parser_version, prompt_tokens,
              completion_tokens, total_tokens, usage_date, created_at
            ) VALUES (
              %(id)s, %(run_id)s, %(nct_id)s, %(parser_version)s,
              %(prompt_tokens)s, %(completion_tokens)s, %(total_tokens)s,
              %(usage_date)s, %(created_at)s
            )
            """,
            {
                "id": str(uuid.uuid4()),
                "run_id": run_id,
                "nct_id": nct_id,
                "parser_version": parser_version,
                "prompt_tokens": prompt_tokens if isinstance(prompt_tokens, int) else None,
                "completion_tokens": (
                    completion_tokens if isinstance(completion_tokens, int) else None
                ),
                "total_tokens": max(total, 0),
                "usage_date": now.date(),
                "created_at": now,
            },
        )


def _compute_coverage_stats(criteria_json: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_rules = len(criteria_json)
    unknown_rules = sum(
        1
        for rule in criteria_json
        if rule.get("field") == "other" or rule.get("certainty") == "low"
    )
    known_rules = total_rules - unknown_rules
    coverage_ratio = float(known_rules) / float(total_rules) if total_rules else 0.0
    return {
        "total_rules": total_rules,
        "known_rules": known_rules,
        "unknown_rules": unknown_rules,
        "failed_rules": unknown_rules,
        "coverage_ratio": round(coverage_ratio, 4),
    }


def _select_recent_trial_nct_ids(
    conn: psycopg.Connection,
    *,
    lookback_hours: int,
    limit: int,
    condition: Optional[str] = None,
    status: Optional[str] = None,
) -> List[str]:
    lookback_hours = max(1, int(lookback_hours))
    limit = max(1, int(limit))
    condition = (condition or "").strip()
    status = (status or "").strip()
    params: Dict[str, Any] = {
        "lookback_hours": lookback_hours,
        "limit": limit,
        "status": status,
    }
    filters: List[str] = [
        "t.fetched_at >= NOW() - make_interval(hours => %(lookback_hours)s)",
    ]
    if condition:
        params["condition_like"] = f"%{condition}%"
        filters.append(
            "("
            "t.title ILIKE %(condition_like)s OR "
            "array_to_string(t.conditions, ',') ILIKE %(condition_like)s"
            ")"
        )
    if status:
        filters.append("t.status = %(status)s")
    where_clause = " AND ".join(filters)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT t.nct_id
            FROM trials AS t
            WHERE {where_clause}
            ORDER BY t.fetched_at DESC
            LIMIT %(limit)s
            """,
            params,
        )
        rows = cur.fetchall()
    return [str(row[0]) for row in rows if row and row[0]]


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

    progressive_backfill = _env_bool("SYNC_PROGRESSIVE_BACKFILL", False)
    refresh_pages = max(1, _env_int("SYNC_REFRESH_PAGES", 1))
    target_trial_total = max(0, _env_int("SYNC_TARGET_TRIAL_TOTAL", 0))
    prune_to_status_filter = _env_bool("SYNC_PRUNE_TO_STATUS_FILTER", False)

    selective_llm_enabled = _env_bool("SYNC_LLM_SELECTIVE", False)
    selective_unknown_ratio_threshold = min(
        1.0,
        max(0.0, _env_float("SYNC_LLM_SELECTIVE_UNKNOWN_RATIO_THRESHOLD", 0.4)),
    )
    selective_unknown_rules_min = max(
        1, _env_int("SYNC_LLM_SELECTIVE_UNKNOWN_RULES_MIN", 2)
    )
    selective_max_llm_calls = max(
        0, _env_int("SYNC_LLM_SELECTIVE_MAX_LLM_CALLS_PER_RUN", 10)
    )
    selective_cooldown_hours = max(
        1, _env_int("SYNC_LLM_SELECTIVE_COOLDOWN_HOURS", 168)
    )
    backfill_enabled = _env_bool("SYNC_LLM_BACKFILL_ENABLED", False)
    backfill_limit = max(0, _env_int("SYNC_LLM_BACKFILL_LIMIT", 20))

    run_id = str(uuid.uuid4())
    client = CTGovClient()

    pages = 0
    processed = 0
    inserted = 0
    updated = 0
    pruned_trials = 0
    pruned_criteria = 0
    inserted_nct_ids: List[str] = []
    backfill_nct_ids: List[str] = []
    parse_success = 0
    parse_failed = 0
    parser_source_breakdown: Dict[str, int] = {}
    fallback_reason_breakdown: Dict[str, int] = {}
    llm_budget_exceeded_count = 0
    backfill_selected = 0
    selective_llm_triggered = 0
    selective_llm_skipped_breakdown: Dict[str, int] = {}
    parser_version = _default_sync_parser_version()

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
            if prune_to_status_filter and status and status.strip():
                allowed_statuses = [
                    entry.strip() for entry in status.split(",") if entry.strip()
                ]
                if allowed_statuses:
                    pruned_criteria, pruned_trials = _prune_trials_to_status_filter(
                        conn,
                        allowed_statuses=allowed_statuses,
                    )

            if progressive_backfill:
                # Always refresh the first N pages so newly added/updated studies
                # get into the DB quickly, then backfill older pages over time.
                refresh_pages = min(page_limit, refresh_pages)
                backfill_pages = max(0, page_limit - refresh_pages)

                cap_reached = False
                if target_trial_total > 0 and _trial_total(conn) >= target_trial_total:
                    cap_reached = True
                    backfill_pages = 0

                next_page_token: Optional[str] = None
                refresh_next_page_token: Optional[str] = None
                for _ in range(refresh_pages):
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
                            inserted_nct_ids.append(str(trial["nct_id"]))
                        else:
                            updated += 1

                    next_page_token = page.get("nextPageToken")
                    refresh_next_page_token = next_page_token
                    if not next_page_token:
                        break

                cursor_written = False
                if not cap_reached and backfill_pages > 0:
                    status_key = _cursor_key_status(status)
                    cursor = _read_sync_cursor(
                        conn,
                        condition=condition,
                        trial_status=status_key,
                    )
                    backfill_token = cursor or refresh_next_page_token
                    if backfill_token:
                        next_page_token = backfill_token
                        for _ in range(backfill_pages):
                            page = client.search_studies(
                                condition=condition,
                                status=status,
                                page_token=next_page_token,
                                page_size=page_size,
                            )
                            pages += 1

                            studies = page.get("studies") or []
                            if not studies:
                                next_page_token = None
                                break

                            for study in studies:
                                trial = _extract_trial(study)
                                is_insert = _upsert_trial(conn, trial)
                                processed += 1
                                if is_insert:
                                    inserted += 1
                                    inserted_nct_ids.append(str(trial["nct_id"]))
                                else:
                                    updated += 1

                            next_page_token = page.get("nextPageToken")
                            if not next_page_token:
                                break

                        _write_sync_cursor(
                            conn,
                            condition=condition,
                            trial_status=status_key,
                            next_page_token=next_page_token,
                        )
                        cursor_written = True

                if cap_reached:
                    LOGGER.info(
                        "sync_trials progressive mode: cap reached target=%s; refresh only",
                        target_trial_total,
                    )
                elif cursor_written:
                    LOGGER.info(
                        "sync_trials progressive mode: cursor updated condition=%s status=%s",
                        condition,
                        status,
                    )
            else:
                next_page_token = None
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
                            inserted_nct_ids.append(str(trial["nct_id"]))
                        else:
                            updated += 1

                    next_page_token = page.get("nextPageToken")
                    if not next_page_token:
                        break

            if backfill_enabled:
                coverage_ratio_threshold = max(
                    0.0, min(1.0, 1.0 - selective_unknown_ratio_threshold)
                )
                backfill_nct_ids = _select_backfill_nct_ids(
                    conn,
                    limit=backfill_limit,
                    coverage_ratio_threshold=coverage_ratio_threshold,
                    cooldown_hours=selective_cooldown_hours,
                )
                if inserted_nct_ids and backfill_nct_ids:
                    inserted_set = {str(nct_id) for nct_id in inserted_nct_ids}
                    backfill_nct_ids = [
                        nct_id
                        for nct_id in backfill_nct_ids
                        if nct_id not in inserted_set
                    ]
                backfill_selected = len(backfill_nct_ids)

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

    selective_llm_ready = bool(
        selective_llm_enabled
        and parser_version == "rule_v1"
        and _env_bool("LLM_PARSER_ENABLED", False)
        and os.getenv("OPENAI_API_KEY")
    )
    recent_llm_usage: set[str] = set()
    if selective_llm_ready and (inserted_nct_ids or backfill_nct_ids):
        with psycopg.connect(database_url) as conn:
            _ensure_tables(conn)
            conn.commit()
            recent_llm_usage = _recent_llm_usage_nct_ids(
                conn,
                nct_ids=[*inserted_nct_ids, *backfill_nct_ids],
                within_hours=selective_cooldown_hours,
            )

    llm_calls_attempted = 0

    def _record_skip(reason: str) -> None:
        selective_llm_skipped_breakdown[reason] = (
            selective_llm_skipped_breakdown.get(reason, 0) + 1
        )

    def _process_nct_id(nct_id: str) -> None:
        nonlocal parse_success
        nonlocal parse_failed
        nonlocal llm_budget_exceeded_count
        nonlocal selective_llm_triggered
        nonlocal llm_calls_attempted

        try:
            rule_stats = parse_trial(nct_id=nct_id, parser_version=parser_version)
        except Exception:
            parse_failed += 1
            LOGGER.exception(
                "auto parse failed run_id=%s nct_id=%s parser_version=%s",
                run_id,
                nct_id,
                parser_version,
            )
            return

        final_stats = rule_stats

        if selective_llm_ready and _should_trigger_selective_llm(
            rule_stats,
            unknown_ratio_threshold=selective_unknown_ratio_threshold,
            unknown_rules_min=selective_unknown_rules_min,
        ):
            if llm_calls_attempted >= selective_max_llm_calls:
                _record_skip("max per run")
            elif nct_id in recent_llm_usage:
                _record_skip("cooldown")
            else:
                llm_calls_attempted += 1
                selective_llm_triggered += 1
                recent_llm_usage.add(nct_id)
                try:
                    final_stats = parse_trial(nct_id=nct_id, parser_version="llm_v1")
                except Exception:
                    _record_skip("llm parse error")
                    LOGGER.exception(
                        "selective llm parse failed run_id=%s nct_id=%s",
                        run_id,
                        nct_id,
                    )

        parse_success += 1
        parser_source = final_stats.parser_source or final_stats.parser_version
        parser_source_breakdown[parser_source] = (
            parser_source_breakdown.get(parser_source, 0) + 1
        )
        if final_stats.fallback_reason:
            fallback_reason_breakdown[final_stats.fallback_reason] = (
                fallback_reason_breakdown.get(final_stats.fallback_reason, 0) + 1
            )
        if final_stats.llm_budget_exceeded:
            llm_budget_exceeded_count += 1

    for nct_id in inserted_nct_ids:
        _process_nct_id(nct_id)

    for nct_id in backfill_nct_ids:
        _process_nct_id(nct_id)

    parse_total = parse_success + parse_failed
    parse_success_rate = (
        round(float(parse_success) / float(parse_total), 4) if parse_total else 0.0
    )

    stats = SyncStats(
        run_id=run_id,
        condition=condition,
        status=status,
        pages=pages,
        processed=processed,
        inserted=inserted,
        updated=updated,
        pruned_trials=pruned_trials,
        pruned_criteria=pruned_criteria,
        parse_success=parse_success,
        parse_failed=parse_failed,
        parse_success_rate=parse_success_rate,
        parser_version=parser_version,
        parser_source_breakdown=parser_source_breakdown,
        fallback_reason_breakdown=fallback_reason_breakdown,
        llm_budget_exceeded_count=llm_budget_exceeded_count,
        backfill_selected=backfill_selected,
        selective_llm_triggered=selective_llm_triggered,
        selective_llm_skipped_breakdown=selective_llm_skipped_breakdown,
    )
    LOGGER.info(
        (
            "sync_trials completed run_id=%s pages=%s processed=%s inserted=%s "
            "updated=%s pruned_trials=%s pruned_criteria=%s "
            "parse_success=%s parse_failed=%s parse_success_rate=%s "
            "parser_version=%s parser_source_breakdown=%s "
            "fallback_reason_breakdown=%s llm_budget_exceeded_count=%s "
            "backfill_selected=%s selective_llm_triggered=%s selective_llm_skipped=%s"
        ),
        run_id,
        pages,
        processed,
        inserted,
        updated,
        pruned_trials,
        pruned_criteria,
        parse_success,
        parse_failed,
        parse_success_rate,
        parser_version,
        parser_source_breakdown,
        fallback_reason_breakdown,
        llm_budget_exceeded_count,
        backfill_selected,
        selective_llm_triggered,
        selective_llm_skipped_breakdown,
    )
    return stats


def reparse_recent_trials(
    *,
    parser_version: str = "llm_v1",
    limit: int = 200,
    lookback_hours: int = 168,
    condition: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL not set")

    selected_nct_ids: List[str] = []
    with psycopg.connect(database_url) as conn:
        _ensure_tables(conn)
        conn.commit()
        selected_nct_ids = _select_recent_trial_nct_ids(
            conn,
            lookback_hours=lookback_hours,
            limit=limit,
            condition=condition,
            status=status,
        )

    parser_source_breakdown: Dict[str, int] = {}
    fallback_reason_breakdown: Dict[str, int] = {}
    llm_budget_exceeded_count = 0
    parsed = 0
    failed = 0

    for nct_id in selected_nct_ids:
        try:
            stats = parse_trial(nct_id=nct_id, parser_version=parser_version)
            parsed += 1
            parser_source = stats.parser_source or parser_version
            parser_source_breakdown[parser_source] = (
                parser_source_breakdown.get(parser_source, 0) + 1
            )
            if stats.fallback_reason:
                fallback_reason_breakdown[stats.fallback_reason] = (
                    fallback_reason_breakdown.get(stats.fallback_reason, 0) + 1
                )
            if stats.llm_budget_exceeded:
                llm_budget_exceeded_count += 1
        except Exception:
            failed += 1
            LOGGER.exception(
                "reparse_recent_trials failed nct_id=%s parser_version=%s",
                nct_id,
                parser_version,
            )

    summary = {
        "selected": len(selected_nct_ids),
        "parsed_success": parsed,
        "parsed_failed": failed,
        "parser_version": parser_version,
        "parser_source_breakdown": parser_source_breakdown,
        "fallback_reason_breakdown": fallback_reason_breakdown,
        "llm_budget_exceeded_count": llm_budget_exceeded_count,
        "lookback_hours": max(1, int(lookback_hours)),
        "condition": (condition or "").strip() or None,
        "status": (status or "").strip() or None,
    }
    LOGGER.info("reparse_recent_trials summary=%s", summary)
    return summary


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

            parser_metadata: Dict[str, Any]
            if parser_version == "rule_v1":
                criteria_json = parse_criteria_v1(trial.get("eligibility_text"))
                parser_metadata = {
                    "parser_source": "rule_v1",
                    "fallback_used": False,
                    "fallback_reason": None,
                    "llm_usage": None,
                }
            elif parser_version == "llm_v1":
                usage_date = dt.datetime.now(dt.UTC).date()
                if _is_llm_budget_exceeded(conn, usage_date):
                    criteria_json = parse_criteria_v1(trial.get("eligibility_text"))
                    parser_metadata = {
                        "parser_source": "rule_v1",
                        "fallback_used": True,
                        "fallback_reason": "llm daily token budget exceeded",
                        "llm_usage": None,
                    }
                else:
                    criteria_json, parser_metadata = (
                        parse_criteria_llm_v1_with_fallback(
                            trial.get("eligibility_text")
                        )
                    )
                    llm_usage = parser_metadata.get("llm_usage")
                    if (
                        isinstance(llm_usage, dict)
                        and isinstance(llm_usage.get("total_tokens"), int)
                        and int(llm_usage.get("total_tokens") or 0) > 0
                    ):
                        _write_llm_usage_log(
                            conn,
                            run_id=run_id,
                            nct_id=nct_id,
                            parser_version=parser_version,
                            usage=llm_usage,
                        )
                daily_tokens_used = _daily_llm_token_usage(conn, usage_date)
                daily_token_budget = _read_llm_daily_token_budget()
                parser_metadata["llm_budget"] = {
                    "daily_token_budget": daily_token_budget,
                    "daily_tokens_used": daily_tokens_used,
                    "budget_exceeded": (
                        daily_token_budget <= 0
                        or daily_tokens_used >= daily_token_budget
                    ),
                }
            else:
                raise ValueError(f"unsupported parser_version: {parser_version}")

            coverage_stats = _compute_coverage_stats(criteria_json)
            coverage_stats.update(parser_metadata)
            unknown_count = int(coverage_stats["unknown_rules"])

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

    parser_source = str(parser_metadata.get("parser_source") or parser_version)
    fallback_used = bool(parser_metadata.get("fallback_used"))
    fallback_reason = parser_metadata.get("fallback_reason")
    llm_budget = parser_metadata.get("llm_budget")
    llm_budget_exceeded = bool(
        isinstance(llm_budget, dict) and llm_budget.get("budget_exceeded")
    )

    stats = ParseStats(
        run_id=run_id,
        nct_id=nct_id,
        parser_version=parser_version,
        status="SUCCESS",
        rule_count=len(criteria_json),
        unknown_count=unknown_count,
        parser_source=parser_source,
        fallback_used=fallback_used,
        fallback_reason=(
            str(fallback_reason) if isinstance(fallback_reason, str) else None
        ),
        llm_budget_exceeded=llm_budget_exceeded,
    )
    LOGGER.info(
        (
            "parse_trial completed run_id=%s nct_id=%s parser_version=%s "
            "parser_source=%s fallback_used=%s fallback_reason=%s "
            "llm_budget_exceeded=%s rules=%s unknown=%s"
        ),
        run_id,
        nct_id,
        parser_version,
        stats.parser_source,
        stats.fallback_used,
        stats.fallback_reason,
        stats.llm_budget_exceeded,
        stats.rule_count,
        stats.unknown_count,
    )
    return stats
