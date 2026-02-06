import datetime as dt
import os
from typing import Any, Dict, Optional

import jwt
from jwt import InvalidTokenError

DEFAULT_ALGORITHM = "HS256"
DEFAULT_JWT_SECRET = "dev-secret-change-me-please-use-32bytes"


class AuthError(Exception):
    """Raised when bearer token auth fails."""


def _jwt_secret() -> str:
    return os.getenv("JWT_SECRET", DEFAULT_JWT_SECRET)


def _jwt_algorithm() -> str:
    return os.getenv("JWT_ALGORITHM", DEFAULT_ALGORITHM)


def create_access_token(
    *,
    sub: str,
    role: str = "user",
    expires_seconds: int = 3600,
) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": sub,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(seconds=expires_seconds)).timestamp()),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=_jwt_algorithm())


def decode_auth_header(authorization: Optional[str]) -> Dict[str, Any]:
    if not authorization:
        raise AuthError("Authorization header is required")

    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthError("Authorization header must be Bearer token")

    token = parts[1].strip()
    if not token:
        raise AuthError("Bearer token is empty")

    try:
        payload = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[_jwt_algorithm()],
        )
    except InvalidTokenError as exc:
        raise AuthError(f"Invalid token: {exc}") from exc

    if not isinstance(payload, dict):
        raise AuthError("Invalid token payload")
    if not payload.get("sub"):
        raise AuthError("Token missing sub claim")
    return payload
