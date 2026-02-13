import os
from typing import Any, Dict, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

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


def _ensure_tables(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(_CREATE_TRIALS_TABLE_SQL)
        conn.exec_driver_sql(_CREATE_TRIAL_CRITERIA_TABLE_SQL)


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


def _build_dataset_meta(engine: Engine) -> Dict[str, Any]:
    summary_stmt = text(
        """
        WITH latest_criteria AS (
          SELECT DISTINCT ON (trial_id)
            trial_id,
            parser_version
          FROM trial_criteria
          ORDER BY trial_id, created_at DESC
        )
        SELECT
          COUNT(*)::BIGINT AS trial_total,
          MAX(t.fetched_at) AS latest_fetched_at,
          COUNT(lc.trial_id)::BIGINT AS trials_with_criteria
        FROM trials AS t
        LEFT JOIN latest_criteria AS lc
          ON lc.trial_id = t.id
        """
    )
    parser_breakdown_stmt = text(
        """
        WITH latest_criteria AS (
          SELECT DISTINCT ON (trial_id)
            trial_id,
            parser_version,
            coverage_stats
          FROM trial_criteria
          ORDER BY trial_id, created_at DESC
        )
        SELECT
          COALESCE(
            NULLIF(coverage_stats->>'parser_source', ''),
            NULLIF(parser_version, ''),
            'unknown'
          ) AS parser_source,
          COUNT(*)::BIGINT AS count
        FROM latest_criteria
        GROUP BY parser_source
        ORDER BY parser_source
        """
    )

    with engine.begin() as conn:
        summary_row = conn.execute(summary_stmt).mappings().first()
        parser_rows = conn.execute(parser_breakdown_stmt).mappings().all()

    trial_total = int(summary_row["trial_total"] or 0) if summary_row else 0
    trials_with_criteria = (
        int(summary_row["trials_with_criteria"] or 0) if summary_row else 0
    )
    latest_fetched_at = (
        summary_row["latest_fetched_at"].isoformat()
        if summary_row and summary_row.get("latest_fetched_at")
        else None
    )

    parser_source_breakdown: Dict[str, int] = {}
    for row in parser_rows:
        source = str(row["parser_source"])
        parser_source_breakdown[source] = int(row["count"] or 0)

    trials_without_criteria = max(0, trial_total - trials_with_criteria)
    coverage_ratio = (
        round(float(trials_with_criteria) / float(trial_total), 4)
        if trial_total > 0
        else 0.0
    )

    return {
        "trial_total": trial_total,
        "latest_fetched_at": latest_fetched_at,
        "criteria_coverage": {
            "trials_with_criteria": trials_with_criteria,
            "trials_without_criteria": trials_without_criteria,
            "coverage_ratio": coverage_ratio,
        },
        "parser_source_breakdown": parser_source_breakdown,
    }


@router.get("/api/system/dataset-meta")
def dataset_meta():
    try:
        engine = _get_engine()
        _ensure_tables(engine)
        data = _build_dataset_meta(engine)
    except (SQLAlchemyError, RuntimeError) as exc:
        return _error("EXTERNAL_API_ERROR", f"Database unavailable: {exc}", 503)

    return _ok(data)
