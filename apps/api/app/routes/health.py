import os
from typing import Tuple

import psycopg
import redis
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"ok": True, "service": "api"}


def _check_postgres() -> Tuple[bool, str | None]:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        return False, "DATABASE_URL not set"
    try:
        with psycopg.connect(dsn, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return True, None
    except Exception as exc:  # pragma: no cover - defensive for runtime readiness
        return False, str(exc)


def _check_redis() -> Tuple[bool, str | None]:
    url = os.getenv("REDIS_URL")
    if not url:
        return False, "REDIS_URL not set"
    try:
        client = redis.Redis.from_url(
            url, socket_connect_timeout=2, socket_timeout=2
        )
        client.ping()
        return True, None
    except Exception as exc:  # pragma: no cover - defensive for runtime readiness
        return False, str(exc)


@router.get("/readyz")
def readyz() -> JSONResponse:
    db_ok, db_err = _check_postgres()
    redis_ok, redis_err = _check_redis()

    checks = {
        "db": {"ok": db_ok},
        "redis": {"ok": redis_ok},
    }
    if db_err:
        checks["db"]["error"] = db_err
    if redis_err:
        checks["redis"]["error"] = redis_err

    ok = db_ok and redis_ok
    status_code = 200 if ok else 503
    return JSONResponse(status_code=status_code, content={"ok": ok, "checks": checks})
