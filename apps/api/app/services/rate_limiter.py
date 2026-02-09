import os
import time
from dataclasses import dataclass

import redis


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int
    retry_after_seconds: int
    backend: str


class FixedWindowRateLimiter:
    def allow(self, *, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        raise NotImplementedError


class InMemoryFixedWindowRateLimiter(FixedWindowRateLimiter):
    def __init__(self) -> None:
        # store_key -> (count, expires_at_epoch)
        self._counts: dict[str, tuple[int, float]] = {}

    def allow(self, *, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        now = time.time()
        window_start = int(now) - (int(now) % window_seconds)
        store_key = f"{key}:{window_start}"

        count, expires_at = self._counts.get(
            store_key,
            (0, window_start + window_seconds + 1),
        )
        if now > expires_at:
            count = 0
            expires_at = window_start + window_seconds + 1

        count += 1
        self._counts[store_key] = (count, expires_at)

        remaining = max(0, limit - count)
        reset_seconds = max(0, int(window_start + window_seconds - now))
        retry_after_seconds = reset_seconds
        return RateLimitDecision(
            allowed=count <= limit,
            limit=limit,
            remaining=remaining,
            reset_seconds=reset_seconds,
            retry_after_seconds=retry_after_seconds,
            backend="memory",
        )


class RedisFixedWindowRateLimiter(FixedWindowRateLimiter):
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def allow(self, *, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        now = int(time.time())
        window_start = now - (now % window_seconds)
        redis_key = f"{key}:{window_start}"

        count = int(self._client.incr(redis_key))
        if count == 1:
            self._client.expire(redis_key, window_seconds + 1)

        remaining = max(0, limit - count)
        reset_seconds = max(0, window_seconds - (now - window_start))
        retry_after_seconds = reset_seconds
        return RateLimitDecision(
            allowed=count <= limit,
            limit=limit,
            remaining=remaining,
            reset_seconds=reset_seconds,
            retry_after_seconds=retry_after_seconds,
            backend="redis",
        )


_MATCH_RATE_LIMITER: FixedWindowRateLimiter | None = None


def get_match_rate_limiter() -> FixedWindowRateLimiter:
    """Best-effort global limiter.

    - Uses Redis when REDIS_URL is configured and reachable.
    - Falls back to an in-memory limiter otherwise.
    """

    global _MATCH_RATE_LIMITER
    if _MATCH_RATE_LIMITER is not None:
        return _MATCH_RATE_LIMITER

    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        _MATCH_RATE_LIMITER = InMemoryFixedWindowRateLimiter()
        return _MATCH_RATE_LIMITER

    try:
        client = redis.Redis.from_url(
            redis_url,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )
        client.ping()
        _MATCH_RATE_LIMITER = RedisFixedWindowRateLimiter(client)
    except redis.RedisError:
        _MATCH_RATE_LIMITER = InMemoryFixedWindowRateLimiter()
    return _MATCH_RATE_LIMITER
