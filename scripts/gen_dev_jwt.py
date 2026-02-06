#!/usr/bin/env python3
"""Generate a development JWT token for local API calls."""

import argparse
import datetime as dt
import os

import jwt


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate dev JWT token")
    parser.add_argument("--sub", default="dev-user", help="subject claim value")
    parser.add_argument("--role", default="user", help="role claim value")
    parser.add_argument(
        "--expires-seconds",
        type=int,
        default=3600,
        help="token lifetime in seconds",
    )
    args = parser.parse_args()

    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": args.sub,
        "role": args.role,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(seconds=args.expires_seconds)).timestamp()),
    }

    secret = os.getenv("JWT_SECRET", "dev-secret-change-me-please-use-32bytes")
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    token = jwt.encode(payload, secret, algorithm=algorithm)
    print(token)


if __name__ == "__main__":
    main()
