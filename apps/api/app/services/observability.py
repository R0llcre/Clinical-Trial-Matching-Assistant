import datetime as dt
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class MatchMetricsSnapshot:
    requests_total: int
    success_total: int
    failure_total: int
    avg_duration_ms: float
    updated_at: Optional[str]


class _MatchMetricsStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests_total = 0
        self._success_total = 0
        self._failure_total = 0
        self._duration_total_ms = 0.0
        self._updated_at: Optional[dt.datetime] = None

    def record(self, *, success: bool, duration_ms: float) -> None:
        bounded_duration_ms = max(float(duration_ms), 0.0)
        with self._lock:
            self._requests_total += 1
            if success:
                self._success_total += 1
            else:
                self._failure_total += 1
            self._duration_total_ms += bounded_duration_ms
            self._updated_at = dt.datetime.now(dt.UTC)

    def snapshot(self) -> MatchMetricsSnapshot:
        with self._lock:
            completed = self._success_total + self._failure_total
            avg_duration_ms = (
                round(self._duration_total_ms / float(completed), 2)
                if completed
                else 0.0
            )
            updated_at = (
                self._updated_at.isoformat().replace("+00:00", "Z")
                if self._updated_at
                else None
            )
            return MatchMetricsSnapshot(
                requests_total=self._requests_total,
                success_total=self._success_total,
                failure_total=self._failure_total,
                avg_duration_ms=avg_duration_ms,
                updated_at=updated_at,
            )

    def reset(self) -> None:
        with self._lock:
            self._requests_total = 0
            self._success_total = 0
            self._failure_total = 0
            self._duration_total_ms = 0.0
            self._updated_at = None


_MATCH_METRICS = _MatchMetricsStore()


def record_match_request(*, success: bool, duration_ms: float) -> None:
    _MATCH_METRICS.record(success=success, duration_ms=duration_ms)


def get_ops_metrics() -> Dict[str, Any]:
    snapshot = _MATCH_METRICS.snapshot()
    return {
        "match": {
            "requests_total": snapshot.requests_total,
            "success_total": snapshot.success_total,
            "failure_total": snapshot.failure_total,
            "avg_duration_ms": snapshot.avg_duration_ms,
        },
        "updated_at": snapshot.updated_at,
    }


def reset_ops_metrics() -> None:
    _MATCH_METRICS.reset()
