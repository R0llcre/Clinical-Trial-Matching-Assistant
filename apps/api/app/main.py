import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from app.routes.auth import router as auth_router
from app.routes.health import router as health_router
from app.routes.matching import router as matching_router
from app.routes.patients import router as patients_router
from app.routes.trials import router as trials_router
from app.services.auth import AuthError, decode_auth_header

app = FastAPI()
_PROTECTED_PREFIXES = ("/api/patients", "/api/match", "/api/matches")


def _load_allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "").strip()
    if not raw:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    if not origins:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_load_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(matching_router)
app.include_router(patients_router)
app.include_router(trials_router)
