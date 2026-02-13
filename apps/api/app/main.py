import json
import logging
import os
import time
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from app.routes.auth import router as auth_router
from app.routes.health import router as health_router
from app.routes.matching import router as matching_router
from app.routes.ops import router as ops_router
from app.routes.patients import router as patients_router
from app.routes.system import router as system_router
from app.routes.trials import router as trials_router
from app.services.auth import AuthError, decode_auth_header

app = FastAPI()
_PROTECTED_PREFIXES = ("/api/patients", "/api/match", "/api/matches")
_REQUEST_ID_HEADER = "X-Request-ID"

LOGGER = logging.getLogger("ctmatch.api")


def _coerce_request_id(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    # Keep it bounded so logs/headers cannot be abused.
    if len(value) > 128:
        return None
    return value


def _new_request_id() -> str:
    return uuid.uuid4().hex


def _load_allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "").strip()
    if not raw:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    if not origins:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    return origins


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.method != "OPTIONS" and request.url.path.startswith(_PROTECTED_PREFIXES):
        try:
            claims = decode_auth_header(request.headers.get("Authorization"))
            request.state.auth_claims = claims
        except AuthError as exc:
            return JSONResponse(
                status_code=401,
                content={
                    "ok": False,
                    "data": None,
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": str(exc),
                        "details": {},
                    },
                },
            )
    return await call_next(request)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = _coerce_request_id(request.headers.get(_REQUEST_ID_HEADER))
    if request_id is None:
        request_id = _new_request_id()
    request.state.request_id = request_id

    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000.0

    response.headers[_REQUEST_ID_HEADER] = request_id

    claims = getattr(request.state, "auth_claims", None)
    subject = claims.get("sub") if isinstance(claims, dict) else None
    LOGGER.info(
        json.dumps(
            {
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "subject": subject,
            }
        )
    )
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=_load_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(matching_router)
app.include_router(ops_router)
app.include_router(patients_router)
app.include_router(system_router)
app.include_router(trials_router)
