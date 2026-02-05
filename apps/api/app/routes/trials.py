import os
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, func, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.services.trial_ingestor import TRIALS_TABLE

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


def _normalize_db_url(database_url: str) -> str:
    # Force psycopg driver instead of SQLAlchemy's psycopg2 default.
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


def _ensure_trials_table(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(_CREATE_TRIALS_TABLE_SQL)


def _error(
    code: str,
    message: str,
    status_code: int,
    details: Optional[Dict[str, Any]] = None,
):
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            },
        },
    )


def _ok(data: Dict[str, Any]) -> JSONResponse:
    return JSONResponse(status_code=200, content={"ok": True, "data": data})


def _parse_pagination(
    page_raw: Optional[str], page_size_raw: Optional[str]
) -> Tuple[int, int]:
    page = int(page_raw) if page_raw is not None else 1
    page_size = int(page_size_raw) if page_size_raw is not None else 20
    if page < 1 or page_size < 1 or page_size > 100:
        raise ValueError("page or page_size out of range")
    return page, page_size


def _format_locations(locations_json: Optional[List[Dict[str, Any]]]) -> List[str]:
    if not locations_json:
        return []
    formatted = []
    for location in locations_json:
        if not isinstance(location, dict):
            continue
        parts = [location.get("city"), location.get("state"), location.get("country")]
        parts = [part for part in parts if part]
        if parts:
            formatted.append(", ".join(parts))
    return formatted


def _search_trials(
    engine: Engine,
    condition: Optional[str],
    status: Optional[str],
    phase: Optional[str],
    country: Optional[str],
    state: Optional[str],
    city: Optional[str],
    page: int,
    page_size: int,
) -> Tuple[List[Dict[str, Any]], int]:
    filters = []
    if condition:
        like = f"%{condition}%"
        filters.append(
            or_(
                TRIALS_TABLE.c.title.ilike(like),
                func.array_to_string(TRIALS_TABLE.c.conditions, ",").ilike(like),
            )
        )
    if status:
        filters.append(TRIALS_TABLE.c.status == status)
    if phase:
        filters.append(TRIALS_TABLE.c.phase == phase)
    if country:
        filters.append(TRIALS_TABLE.c.locations_json.contains([{"country": country}]))
    if state:
        filters.append(TRIALS_TABLE.c.locations_json.contains([{"state": state}]))
    if city:
        filters.append(TRIALS_TABLE.c.locations_json.contains([{"city": city}]))

    columns = [
        TRIALS_TABLE.c.nct_id,
        TRIALS_TABLE.c.title,
        TRIALS_TABLE.c.status,
        TRIALS_TABLE.c.phase,
        TRIALS_TABLE.c.conditions,
        TRIALS_TABLE.c.locations_json,
        TRIALS_TABLE.c.fetched_at,
    ]

    stmt = select(*columns)
    if filters:
        stmt = stmt.where(*filters)
    stmt = (
        stmt.order_by(TRIALS_TABLE.c.fetched_at.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )

    count_stmt = select(func.count()).select_from(TRIALS_TABLE)
    if filters:
        count_stmt = count_stmt.where(*filters)

    with engine.begin() as conn:
        total = conn.execute(count_stmt).scalar_one()
        rows = conn.execute(stmt).mappings().all()

    trials = []
    for row in rows:
        trials.append(
            {
                "nct_id": row["nct_id"],
                "title": row["title"],
                "status": row["status"],
                "phase": row["phase"],
                "conditions": row["conditions"] or [],
                "locations": _format_locations(row["locations_json"]),
                "fetched_at": (
                    row["fetched_at"].isoformat() if row["fetched_at"] else None
                ),
            }
        )

    return trials, int(total)


def _get_trial(engine: Engine, nct_id: str) -> Optional[Dict[str, Any]]:
    stmt = select(TRIALS_TABLE).where(TRIALS_TABLE.c.nct_id == nct_id).limit(1)
    with engine.begin() as conn:
        row = conn.execute(stmt).mappings().first()

    if not row:
        return None

    raw_json = row.get("raw_json") or {}
    summary = (
        raw_json.get("protocolSection", {})
        .get("descriptionModule", {})
        .get("briefSummary")
    )

    return {
        "nct_id": row["nct_id"],
        "title": row["title"],
        "summary": summary,
        "status": row["status"],
        "phase": row["phase"],
        "conditions": row["conditions"] or [],
        "eligibility_text": row["eligibility_text"],
        "locations": _format_locations(row["locations_json"]),
        "fetched_at": row["fetched_at"].isoformat() if row["fetched_at"] else None,
    }


@router.get("/api/trials")
def list_trials(
    condition: Optional[str] = None,
    status: Optional[str] = None,
    phase: Optional[str] = None,
    country: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    page: Optional[str] = None,
    page_size: Optional[str] = None,
):
    """Return a filtered, paginated trial list."""
    try:
        page_num, page_size_num = _parse_pagination(page, page_size)
    except (ValueError, TypeError):
        return _error(
            "VALIDATION_ERROR",
            "page and page_size must be valid integers between 1 and 100",
            400,
            {"page": page, "page_size": page_size},
        )

    try:
        engine = _get_engine()
        _ensure_trials_table(engine)
        trials, total = _search_trials(
            engine,
            condition=condition,
            status=status,
            phase=phase,
            country=country,
            state=state,
            city=city,
            page=page_num,
            page_size=page_size_num,
        )
    except (SQLAlchemyError, RuntimeError) as exc:
        return _error("EXTERNAL_API_ERROR", f"Database unavailable: {exc}", 503)

    return _ok(
        {
            "trials": trials,
            "total": total,
            "page": page_num,
            "page_size": page_size_num,
        }
    )


@router.get("/api/trials/{nct_id}")
def get_trial(nct_id: str):
    """Return trial details for a specific NCT ID."""
    try:
        engine = _get_engine()
        _ensure_trials_table(engine)
        trial = _get_trial(engine, nct_id)
    except (SQLAlchemyError, RuntimeError) as exc:
        return _error("EXTERNAL_API_ERROR", f"Database unavailable: {exc}", 503)

    if not trial:
        return _error(
            "TRIAL_NOT_FOUND",
            "trial not found",
            404,
            {"nct_id": nct_id},
        )

    return _ok(trial)
