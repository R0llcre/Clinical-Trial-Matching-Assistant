import os
import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services.auth import create_access_token

router = APIRouter()


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


def _error(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "data": None,
            "error": {
                "code": code,
                "message": message,
                "details": {},
            },
        },
    )


@router.get("/api/auth/preview-token")
def get_preview_token(sub: str | None = None) -> JSONResponse:
    """Issue a short-lived token for preview/demo environments.

    This endpoint is disabled by default and must be explicitly enabled via
    CTMA_PREVIEW_TOKEN_ENABLED=1.
    """
    if not _env_bool("CTMA_PREVIEW_TOKEN_ENABLED", False):
        return _error("NOT_FOUND", "not found", 404)

    expires_seconds = _env_int("CTMA_PREVIEW_TOKEN_EXPIRES_SECONDS", 86400)
    if expires_seconds < 60 or expires_seconds > 60 * 60 * 24 * 30:
        expires_seconds = 86400

    subject = os.getenv("CTMA_PREVIEW_TOKEN_SUB", "preview-user")
    sub_value = (sub or "").strip()
    if sub_value:
        try:
            subject = str(uuid.UUID(sub_value))
        except ValueError:
            # Keep the default behavior when sub is invalid.
            subject = os.getenv("CTMA_PREVIEW_TOKEN_SUB", "preview-user")

    token = create_access_token(
        sub=subject,
        role=os.getenv("CTMA_PREVIEW_TOKEN_ROLE", "preview"),
        expires_seconds=expires_seconds,
    )
    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "data": {
                "token": token,
                "expires_seconds": expires_seconds,
            },
            "error": None,
        },
    )
