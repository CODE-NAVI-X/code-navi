"""In-process sliding-window rate limiter for auth endpoints.

Limitations: single-instance only; state not persisted. Multi-instance
deployments require an external store (e.g., Redis). This is documented
as a known limitation in the delivery report.
"""

from __future__ import annotations

import os
import time
from collections import deque
from threading import Lock


class _Bucket:
    """Stores timestamps for a single (key, window) pair."""

    def __init__(self) -> None:
        self._timestamps: deque[float] = deque()
        self._lock = Lock()

    def add_and_check(self, now: float, window_seconds: int, limit: int) -> bool:
        """Record a hit and return True if within limit, False if exceeded."""
        with self._lock:
            # Evict old entries
            cutoff = now - window_seconds
            while self._timestamps and self._timestamps[0] < cutoff:
                self._timestamps.popleft()
            if len(self._timestamps) >= limit:
                return False
            self._timestamps.append(now)
            return True


class InProcessRateLimiter:
    """Per-(ip, email) and pure-IP sliding-window rate limiter."""

    def __init__(
        self,
        per_minute_limit: int | None = None,
        per_15min_limit: int | None = None,
        per_ip_minute_limit: int | None = None,
    ) -> None:
        env_min = os.getenv("CODE_NAVI_RATE_LIMIT_PER_MINUTE")
        env_15 = os.getenv("CODE_NAVI_RATE_LIMIT_PER_15MIN")
        env_ip_min = os.getenv("CODE_NAVI_RATE_LIMIT_IP_PER_MINUTE")
        self._per_minute = per_minute_limit or (int(env_min) if env_min else 5)
        self._per_15min = per_15min_limit or (int(env_15) if env_15 else 20)
        self._per_ip_minute = per_ip_minute_limit or (int(env_ip_min) if env_ip_min else 20)
        self._buckets_1m: dict[str, _Bucket] = {}
        self._buckets_15m: dict[str, _Bucket] = {}
        self._buckets_ip_1m: dict[str, _Bucket] = {}
        self._lock = Lock()

    def reset(self) -> None:
        """Clear all rate limit buckets (useful for tests and maintenance)."""
        with self._lock:
            self._buckets_1m.clear()
            self._buckets_15m.clear()
            self._buckets_ip_1m.clear()

    def _get_bucket(self, store: dict[str, _Bucket], key: str) -> _Bucket:
        with self._lock:
            if key not in store:
                store[key] = _Bucket()
            return store[key]

    def check(self, ip: str, identifier: str) -> bool:
        """Return True if the request is within limits, False if rate-limited."""
        now = time.monotonic()
        # 1. Pure IP limit
        ok_ip = self._get_bucket(self._buckets_ip_1m, ip).add_and_check(
            now, 60, self._per_ip_minute
        )
        # 2. IP:Identifier compound limits
        key = f"{ip}:{identifier}"
        ok_1m = self._get_bucket(self._buckets_1m, key).add_and_check(
            now, 60, self._per_minute
        )
        ok_15m = self._get_bucket(self._buckets_15m, key).add_and_check(
            now, 900, self._per_15min
        )
        return ok_ip and ok_1m and ok_15m


# Module-level singleton
_limiter = InProcessRateLimiter()


def get_rate_limiter() -> InProcessRateLimiter:
    """FastAPI dependency: returns the shared rate limiter."""
    return _limiter