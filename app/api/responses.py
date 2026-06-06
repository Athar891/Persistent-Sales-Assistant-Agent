"""Helpers for building the response envelope's `meta` block from request state."""

import time
from datetime import UTC, datetime

from fastapi import Request

from app.models.envelope import Meta


def build_meta(request: Request, *, session_id: str | None = None) -> Meta:
    start = getattr(request.state, "start", None)
    latency_ms = int((time.perf_counter() - start) * 1000) if start is not None else 0
    return Meta(
        request_id=getattr(request.state, "request_id", "unknown"),
        session_id=session_id,
        timestamp=datetime.now(UTC),
        latency_ms=latency_ms,
    )
