from fastapi import FastAPI
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from app.routes.health import router as health_router
from app.routes.matching import router as matching_router
from app.routes.patients import router as patients_router
from app.routes.trials import router as trials_router
from app.services.auth import AuthError, decode_auth_header

app = FastAPI()
_PROTECTED_PREFIXES = ("/api/patients", "/api/match", "/api/matches")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path.startswith(_PROTECTED_PREFIXES):
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
app.include_router(matching_router)
app.include_router(patients_router)
app.include_router(trials_router)
