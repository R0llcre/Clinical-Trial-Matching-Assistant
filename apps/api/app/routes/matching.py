import datetime as dt
import os
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from psycopg.types.json import Json
from sqlalchemy import text
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError

from app.services.matching_engine import match_trials

router = APIRouter()

_ENGINE: Optional[Engine] = None

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


def _ensure_match_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(_CREATE_TRIALS_TABLE_SQL)
        conn.exec_driver_sql(_CREATE_PATIENT_PROFILES_TABLE_SQL)
        conn.exec_driver_sql(_CREATE_MATCHES_TABLE_SQL)


def _load_patient_profile(
    engine: Engine, patient_profile_id: str
) -> Optional[Dict[str, Any]]:
    stmt = text(
        """
        SELECT profile_json
        FROM patient_profiles
        WHERE id = :id
        LIMIT 1
        """
    )
    with engine.begin() as conn:
        row = conn.execute(stmt, {"id": patient_profile_id}).mappings().first()
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
                "user_id": None,
                "patient_profile_id": patient_profile_id,
                "query_json": Json({"filters": filters, "top_k": top_k}),
                "results_json": Json(results),
                "created_at": dt.datetime.utcnow(),
            },
        )


def _get_match_by_id(engine: Engine, match_id: str) -> Optional[Dict[str, Any]]:
    stmt = text(
        """
        SELECT id, patient_profile_id, query_json, results_json, created_at
        FROM matches
        WHERE id = :id
        LIMIT 1
        """
    )
    with engine.begin() as conn:
        row = conn.execute(stmt, {"id": match_id}).mappings().first()
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


@router.post("/api/match")
def create_match(payload: Dict[str, Any]):
    patient_profile_id = payload.get("patient_profile_id")
    filters = payload.get("filters") or {}
    top_k = payload.get("top_k", 10)

    if not isinstance(patient_profile_id, str) or not patient_profile_id.strip():
        return _error(
            "VALIDATION_ERROR",
            "patient_profile_id is required",
            400,
            {"patient_profile_id": patient_profile_id},
        )

    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1 or top_k > 50:
        return _error(
            "VALIDATION_ERROR",
            "top_k must be an integer between 1 and 50",
            400,
            {"top_k": top_k},
        )

    if not isinstance(filters, dict):
        return _error(
            "VALIDATION_ERROR",
            "filters must be a JSON object",
            400,
            {"filters": filters},
        )

    try:
        engine = _get_engine()
        _ensure_match_tables(engine)
        patient_profile = _load_patient_profile(engine, patient_profile_id.strip())
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
            filters=filters,
            top_k=top_k,
            results=results,
        )
    except (SQLAlchemyError, RuntimeError) as exc:
        return _error("EXTERNAL_API_ERROR", f"Database unavailable: {exc}", 503)

    return _ok({"match_id": match_id, "results": results})


@router.get("/api/matches/{match_id}")
def get_match(match_id: str):
    try:
        engine = _get_engine()
        _ensure_match_tables(engine)
        match = _get_match_by_id(engine, match_id)
    except (SQLAlchemyError, RuntimeError) as exc:
        return _error("EXTERNAL_API_ERROR", f"Database unavailable: {exc}", 503)

    if not match:
        return _error("MATCH_NOT_FOUND", "match not found", 404, {"id": match_id})

    return _ok(match)
