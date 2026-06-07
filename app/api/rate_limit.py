"""In-process sliding-window rate limiter.

State lives in this process, which is correct for the single-worker Railway deployment.
At multi-worker or multi-replica scale, swap this for a shared store (e.g. Redis) behind
the same ``check()`` interface — the middleware that calls it never changes.
"""

from time import monotonic


class RateLimiter:
    """Allow up to ``max_per_minute`` hits per key within a rolling window."""

    def __init__(self, max_per_minute: int, *, window_seconds: float = 60.0) -> None:
        self._max = max_per_minute
        self._window = window_seconds
        self._hits: dict[str, list[float]] = {}

    def check(self, key: str, *, now: float | None = None) -> tuple[bool, float]:
        """Record a hit for ``key``. Returns ``(allowed, retry_after_seconds)``.

        ``now`` is injectable so tests stay deterministic without sleeping.
        """
        if self._max <= 0:
            return True, 0.0  # limiter disabled
        t = monotonic() if now is None else now
        cutoff = t - self._window
        bucket = self._hits.setdefault(key, [])
        bucket[:] = [ts for ts in bucket if ts > cutoff]  # drop hits outside the window
        if len(bucket) >= self._max:
            retry_after = self._window - (t - bucket[0])
            return False, max(retry_after, 0.0)
        bucket.append(t)
        return True, 0.0
