import datetime as dt
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, func, insert, select, update
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.schema import Column, MetaData, Table
from sqlalchemy.types import TIMESTAMP, Text

router = APIRouter()

_ENGINE: Optional[Engine] = None

_METADATA = MetaData()

PATIENT_PROFILES_TABLE = Table(
    "patient_profiles",
    _METADATA,
    Column("id", UUID(as_uuid=False), primary_key=True),
    Column("user_id", UUID(as_uuid=False), nullable=True),
    Column("profile_json", JSONB, nullable=False),
    Column("source", Text, nullable=False),
    Column("created_at", TIMESTAMP, nullable=False),
    Column("updated_at", TIMESTAMP, nullable=False),
)

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


def _ensure_patient_profiles_table(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(_CREATE_PATIENT_PROFILES_TABLE_SQL)


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


def _parse_pagination(
    page_raw: Optional[str], page_size_raw: Optional[str]
) -> Tuple[int, int]:
    page = int(page_raw) if page_raw is not None else 1
    page_size = int(page_size_raw) if page_size_raw is not None else 20
    if page < 1 or page_size < 1 or page_size > 100:
        raise ValueError("page or page_size out of range")
    return page, page_size


def _validate_profile_json(profile_json: Any) -> None:
    if not isinstance(profile_json, dict):
        raise ValueError("profile_json must be a JSON object")

    demographics = profile_json.get("demographics")
    if not isinstance(demographics, dict):
        raise ValueError("demographics is required")

    age = demographics.get("age")
    if isinstance(age, bool) or not isinstance(age, (int, float)):
        raise ValueError("demographics.age is required")
    if int(age) < 0:
        raise ValueError("demographics.age must be >= 0")

    sex = demographics.get("sex")
    if not isinstance(sex, str) or not sex.strip():
        raise ValueError("demographics.sex is required")


def _serialize_patient(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "source": row["source"],
        "profile_json": row["profile_json"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


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


def _create_patient(
    engine: Engine, profile_json: Dict[str, Any], source: str, user_id: str
) -> Dict[str, Any]:
    now = dt.datetime.utcnow()
    payload = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "profile_json": profile_json,
        "source": source,
        "created_at": now,
        "updated_at": now,
    }
    stmt = insert(PATIENT_PROFILES_TABLE).values(**payload)

    with engine.begin() as conn:
        conn.execute(stmt)

    return _serialize_patient(payload)


def _get_patient(
    engine: Engine, patient_id: str, user_id: str
) -> Optional[Dict[str, Any]]:
    stmt = (
        select(PATIENT_PROFILES_TABLE)
        .where(PATIENT_PROFILES_TABLE.c.id == patient_id)
        .where(PATIENT_PROFILES_TABLE.c.user_id == user_id)
        .limit(1)
    )
    with engine.begin() as conn:
        row = conn.execute(stmt).mappings().first()
    if not row:
        return None
    return _serialize_patient(dict(row))


def _update_patient(
    engine: Engine,
    patient_id: str,
    profile_json: Dict[str, Any],
    source: str,
    user_id: str,
) -> Optional[Dict[str, Any]]:
    now = dt.datetime.utcnow()

    stmt = (
        update(PATIENT_PROFILES_TABLE)
        .where(PATIENT_PROFILES_TABLE.c.id == patient_id)
        .where(PATIENT_PROFILES_TABLE.c.user_id == user_id)
        .values(profile_json=profile_json, source=source, updated_at=now)
    )
    with engine.begin() as conn:
        result = conn.execute(stmt)
        if result.rowcount == 0:
            return None

    return _get_patient(engine, patient_id, user_id)


def _list_patients(
    engine: Engine, page: int, page_size: int, user_id: str
) -> Tuple[List[Dict[str, Any]], int]:
    stmt = (
        select(PATIENT_PROFILES_TABLE)
        .where(PATIENT_PROFILES_TABLE.c.user_id == user_id)
        .order_by(PATIENT_PROFILES_TABLE.c.created_at.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    count_stmt = (
        select(func.count())
        .select_from(PATIENT_PROFILES_TABLE)
        .where(PATIENT_PROFILES_TABLE.c.user_id == user_id)
    )

    with engine.begin() as conn:
        total = conn.execute(count_stmt).scalar_one()
        rows = conn.execute(stmt).mappings().all()

    patients = [_serialize_patient(dict(row)) for row in rows]
    return patients, int(total)


@router.post("/api/patients")
def create_patient(payload: Dict[str, Any], request: Request):
    profile_json = payload.get("profile_json")
    source = payload.get("source", "manual")

    user_id = _user_id_from_request(request)
    if not user_id:
        return _error("UNAUTHORIZED", "invalid auth subject", 401)

    try:
        _validate_profile_json(profile_json)
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source must be a non-empty string")
        source = source.strip()
    except (ValueError, TypeError) as exc:
        return _error(
            "VALIDATION_ERROR",
            str(exc),
            400,
            {
                "fields": [
                    "profile_json.demographics.age",
                    "profile_json.demographics.sex",
                ]
            },
        )

    try:
        engine = _get_engine()
        _ensure_patient_profiles_table(engine)
        patient = _create_patient(engine, profile_json, source, user_id)
    except (SQLAlchemyError, RuntimeError) as exc:
        return _error("EXTERNAL_API_ERROR", f"Database unavailable: {exc}", 503)

    return _ok(patient)


@router.put("/api/patients/{patient_id}")
def update_patient(patient_id: str, payload: Dict[str, Any], request: Request):
    profile_json = payload.get("profile_json")
    source = payload.get("source", "manual")

    user_id = _user_id_from_request(request)
    if not user_id:
        return _error("UNAUTHORIZED", "invalid auth subject", 401)

    try:
        _validate_profile_json(profile_json)
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source must be a non-empty string")
        source = source.strip()
    except (ValueError, TypeError) as exc:
        return _error(
            "VALIDATION_ERROR",
            str(exc),
            400,
            {
                "fields": [
                    "profile_json.demographics.age",
                    "profile_json.demographics.sex",
                ]
            },
        )

    try:
        engine = _get_engine()
        _ensure_patient_profiles_table(engine)
        patient = _update_patient(engine, patient_id, profile_json, source, user_id)
    except (SQLAlchemyError, RuntimeError) as exc:
        return _error("EXTERNAL_API_ERROR", f"Database unavailable: {exc}", 503)

    if not patient:
        return _error(
            "PATIENT_NOT_FOUND",
            "patient profile not found",
            404,
            {"id": patient_id},
        )

    return _ok(patient)


@router.get("/api/patients/{patient_id}")
def get_patient(patient_id: str, request: Request):
    user_id = _user_id_from_request(request)
    if not user_id:
        return _error("UNAUTHORIZED", "invalid auth subject", 401)

    try:
        engine = _get_engine()
        _ensure_patient_profiles_table(engine)
        patient = _get_patient(engine, patient_id, user_id)
    except (SQLAlchemyError, RuntimeError) as exc:
        return _error("EXTERNAL_API_ERROR", f"Database unavailable: {exc}", 503)

    if not patient:
        return _error(
            "PATIENT_NOT_FOUND",
            "patient profile not found",
            404,
            {"id": patient_id},
        )

    return _ok(patient)


@router.get("/api/patients")
def list_patients(
    request: Request, page: Optional[str] = None, page_size: Optional[str] = None
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

    try:
        engine = _get_engine()
        _ensure_patient_profiles_table(engine)
        patients, total = _list_patients(engine, page_num, page_size_num, user_id)
    except (SQLAlchemyError, RuntimeError) as exc:
        return _error("EXTERNAL_API_ERROR", f"Database unavailable: {exc}", 503)

    return _ok(
        {
            "patients": patients,
            "total": total,
            "page": page_num,
            "page_size": page_size_num,
        }
    )
