import datetime as dt
import os
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from psycopg.types.json import Json
from sqlalchemy import text
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError

from app.services.matching_engine import match_trials
from app.services.observability import record_match_request
from app.services.rate_limiter import get_match_rate_limiter

router = APIRouter()

_ENGINE: Optional[Engine] = None
_ALLOWED_FILTER_KEYS = ("condition", "status", "phase", "country", "state", "city")

_CREATE_TRIALS_TABLE_SQL = """
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

_CREATE_PATIENT_PROFILES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS patient_profiles (
  id UUID PRIMARY KEY,
  user_id UUID,
  profile_json JSONB NOT NULL,
  source TEXT NOT NULL DEFAULT 'manual',
  created_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL
)
"""

_CREATE_MATCHES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS matches (
  id UUID PRIMARY KEY,
  user_id UUID,
  patient_profile_id UUID NOT NULL,
  query_json JSONB NOT NULL,
  results_json JSONB NOT NULL,
  created_at TIMESTAMP NOT NULL
)
"""

_CREATE_TRIAL_CRITERIA_TABLE_SQL = """
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


def _normalize_db_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def _get_engine() -> Engine:
    global _ENGINE
    if _ENGINE is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL not set")
        _ENGINE = create_engine(_normalize_db_url(database_url), pool_pre_ping=True)
    return _ENGINE


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _rate_limit_key(request: Request) -> str:
    claims = getattr(request.state, "auth_claims", None)
    subject = claims.get("sub") if isinstance(claims, dict) else None
    if subject:
        client_id = f"sub:{subject}"
    else:
        xff = request.headers.get("x-forwarded-for")
        ip = (
            xff.split(",")[0].strip()
            if xff
            else (request.client.host if request.client else "unknown")
        )
        client_id = f"ip:{ip}"
    return f"ratelimit:match:{client_id}"


def _user_id_from_request(request: Request) -> Optional[str]:
    claims = getattr(request.state, "auth_claims", None)
    if not isinstance(claims, dict):
        return None
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        return None
    try:
        return str(uuid.UUID(subject.strip()))
    except ValueError:
        return None


def _ensure_match_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(_CREATE_TRIALS_TABLE_SQL)
        conn.exec_driver_sql(_CREATE_PATIENT_PROFILES_TABLE_SQL)
        conn.exec_driver_sql(_CREATE_MATCHES_TABLE_SQL)
        conn.exec_driver_sql(_CREATE_TRIAL_CRITERIA_TABLE_SQL)


def _load_patient_profile(
    engine: Engine, patient_profile_id: str, user_id: str
) -> Optional[Dict[str, Any]]:
    stmt = text(
        """
        SELECT profile_json
        FROM patient_profiles
        WHERE id = :id AND user_id = :user_id
        LIMIT 1
        """
    )
    with engine.begin() as conn:
        row = conn.execute(
            stmt, {"id": patient_profile_id, "user_id": user_id}
        ).mappings().first()
    if not row:
        return None
    profile_json = row.get("profile_json")
    if not isinstance(profile_json, dict):
        return None
    return profile_json


def _error(
    code: str,
    message: str,
    status_code: int,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "data": None,
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            },
        },
    )


def _ok(data: Dict[str, Any]) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={"ok": True, "data": data, "error": None},
    )


def _save_match_result(
    engine: Engine,
    *,
    match_id: str,
    patient_profile_id: str,
    user_id: str,
    filters: Dict[str, Any],
    top_k: int,
    results: list[Dict[str, Any]],
) -> None:
    stmt = text(
        """
        INSERT INTO matches (
            id, user_id, patient_profile_id, query_json, results_json, created_at
        ) VALUES (
            :id, :user_id, :patient_profile_id, :query_json, :results_json, :created_at
        )
        """
    )
    with engine.begin() as conn:
        conn.execute(
            stmt,
            {
                "id": match_id,
                "user_id": user_id,
                "patient_profile_id": patient_profile_id,
                "query_json": Json({"filters": filters, "top_k": top_k}),
                "results_json": Json(results),
                "created_at": dt.datetime.utcnow(),
            },
        )


def _normalize_filters(raw_filters: Any) -> Dict[str, str]:
    if raw_filters is None:
        return {}
    if not isinstance(raw_filters, dict):
        raise ValueError("filters must be a JSON object")

    normalized: Dict[str, str] = {}
    for key in _ALLOWED_FILTER_KEYS:
        value = raw_filters.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, str):
            raise ValueError(f"filters.{key} must be a string")
        trimmed = value.strip()
        if trimmed:
            normalized[key] = trimmed
    return normalized


def _parse_pagination(
    page_raw: Optional[str], page_size_raw: Optional[str]
) -> tuple[int, int]:
    page = int(page_raw) if page_raw is not None else 1
    page_size = int(page_size_raw) if page_size_raw is not None else 20
    if page < 1 or page_size < 1 or page_size > 100:
        raise ValueError("page or page_size out of range")
    return page, page_size


def _get_match_by_id(
    engine: Engine, match_id: str, user_id: str
) -> Optional[Dict[str, Any]]:
    stmt = text(
        """
        SELECT id, patient_profile_id, query_json, results_json, created_at
        FROM matches
        WHERE id = :id AND user_id = :user_id
        LIMIT 1
        """
    )
    with engine.begin() as conn:
        row = (
            conn.execute(stmt, {"id": match_id, "user_id": user_id})
            .mappings()
            .first()
        )
    if not row:
        return None
    return {
        "id": str(row["id"]),
        "patient_profile_id": str(row["patient_profile_id"]),
        "query_json": row["query_json"],
        "results": row["results_json"],
        "created_at": (
            row["created_at"].isoformat() if row["created_at"] else None
        ),
    }


def _list_matches(
    engine: Engine,
    *,
    user_id: str,
    patient_profile_id: Optional[str],
    page: int,
    page_size: int,
) -> tuple[list[Dict[str, Any]], int]:
    where = "user_id = :user_id"
    base_params: Dict[str, Any] = {"user_id": user_id}
    if patient_profile_id:
        where += " AND patient_profile_id = :patient_profile_id"
        base_params["patient_profile_id"] = patient_profile_id

    stmt_params: Dict[str, Any] = {
        **base_params,
        "limit": page_size,
        "offset": (page - 1) * page_size,
    }

    stmt = text(
        f"""
        SELECT id, patient_profile_id, query_json, created_at
        FROM matches
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    count_stmt = text(f"SELECT count(*) AS total FROM matches WHERE {where}")

    with engine.begin() as conn:
        total = conn.execute(count_stmt, base_params).mappings().first()
        rows = conn.execute(stmt, stmt_params).mappings().all()

    total_value = int(total["total"]) if total and total.get("total") is not None else 0
    matches = [
        {
            "id": str(row["id"]),
            "patient_profile_id": str(row["patient_profile_id"]),
            "query_json": row["query_json"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
        for row in rows
    ]
    return matches, total_value


@router.get("/api/matches")
def list_matches(
    request: Request,
    patient_profile_id: Optional[str] = None,
    page: Optional[str] = None,
    page_size: Optional[str] = None,
):
    user_id = _user_id_from_request(request)
    if not user_id:
        return _error("UNAUTHORIZED", "invalid auth subject", 401)

    try:
        page_num, page_size_num = _parse_pagination(page, page_size)
    except (ValueError, TypeError):
        return _error(
            "VALIDATION_ERROR",
            "page and page_size must be valid integers between 1 and 100",
            400,
            {"page": page, "page_size": page_size},
        )

    normalized_patient_id: Optional[str] = None
    if patient_profile_id is not None:
        raw = patient_profile_id.strip()
        if raw:
            try:
                normalized_patient_id = str(uuid.UUID(raw))
            except ValueError:
                return _error(
                    "VALIDATION_ERROR",
                    "patient_profile_id must be a valid UUID",
                    400,
                    {"patient_profile_id": patient_profile_id},
                )

    try:
        engine = _get_engine()
        _ensure_match_tables(engine)
        matches, total = _list_matches(
            engine,
            user_id=user_id,
            patient_profile_id=normalized_patient_id,
            page=page_num,
            page_size=page_size_num,
        )
    except (SQLAlchemyError, RuntimeError) as exc:
        return _error("EXTERNAL_API_ERROR", f"Database unavailable: {exc}", 503)

    return _ok(
        {
            "matches": matches,
            "total": total,
            "page": page_num,
            "page_size": page_size_num,
        }
    )


@router.post("/api/match")
def create_match(payload: Dict[str, Any], request: Request):
    start = time.perf_counter()
    success = False

    try:
        user_id = _user_id_from_request(request)
        if not user_id:
            return _error("UNAUTHORIZED", "invalid auth subject", 401)

        patient_profile_id = payload.get("patient_profile_id")
        raw_filters = payload.get("filters")
        top_k = payload.get("top_k", 10)

        if not isinstance(patient_profile_id, str) or not patient_profile_id.strip():
            return _error(
                "VALIDATION_ERROR",
                "patient_profile_id is required",
                400,
                {"patient_profile_id": patient_profile_id},
            )

        if (
            isinstance(top_k, bool)
            or not isinstance(top_k, int)
            or top_k < 1
            or top_k > 50
        ):
            return _error(
                "VALIDATION_ERROR",
                "top_k must be an integer between 1 and 50",
                400,
                {"top_k": top_k},
            )

        try:
            filters = _normalize_filters(raw_filters)
        except ValueError as exc:
            return _error(
                "VALIDATION_ERROR",
                str(exc),
                400,
                {"filters": raw_filters},
            )

        limit_per_minute = _env_int("MATCH_RATE_LIMIT_PER_MINUTE", 30)
        if limit_per_minute > 0:
            decision = get_match_rate_limiter().allow(
                key=_rate_limit_key(request),
                limit=limit_per_minute,
                window_seconds=60,
            )
            if not decision.allowed:
                response = _error(
                    "RATE_LIMITED",
                    "too many match requests; please retry later",
                    429,
                    {
                        "limit": decision.limit,
                        "remaining": decision.remaining,
                        "reset_seconds": decision.reset_seconds,
                        "backend": decision.backend,
                    },
                )
                response.headers["Retry-After"] = str(decision.retry_after_seconds)
                response.headers["X-RateLimit-Limit"] = str(decision.limit)
                response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
                response.headers["X-RateLimit-Reset"] = str(decision.reset_seconds)
                return response

        engine = _get_engine()
        _ensure_match_tables(engine)
        patient_profile = _load_patient_profile(
            engine, patient_profile_id.strip(), user_id
        )
        if not patient_profile:
            return _error(
                "PATIENT_NOT_FOUND",
                "patient profile not found",
                404,
                {"patient_profile_id": patient_profile_id},
            )

        results = match_trials(
            engine,
            patient_profile,
            filters=filters,
            top_k=top_k,
        )
        match_id = str(uuid.uuid4())
        _save_match_result(
            engine,
            match_id=match_id,
            patient_profile_id=patient_profile_id.strip(),
            user_id=user_id,
            filters=filters,
            top_k=top_k,
            results=results,
        )
        success = True
        return _ok({"match_id": match_id, "results": results})
    except (SQLAlchemyError, RuntimeError) as exc:
        return _error("EXTERNAL_API_ERROR", f"Database unavailable: {exc}", 503)

    finally:
        duration_ms = (time.perf_counter() - start) * 1000.0
        record_match_request(success=success, duration_ms=duration_ms)


@router.get("/api/matches/{match_id}")
def get_match(match_id: str, request: Request):
    user_id = _user_id_from_request(request)
    if not user_id:
        return _error("UNAUTHORIZED", "invalid auth subject", 401)

    try:
        engine = _get_engine()
        _ensure_match_tables(engine)
        match = _get_match_by_id(engine, match_id, user_id)
    except (SQLAlchemyError, RuntimeError) as exc:
        return _error("EXTERNAL_API_ERROR", f"Database unavailable: {exc}", 503)

    if not match:
        return _error("MATCH_NOT_FOUND", "match not found", 404, {"id": match_id})

    return _ok(match)
