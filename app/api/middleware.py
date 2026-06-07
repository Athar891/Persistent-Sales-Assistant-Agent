"""Request-context middleware: request_id, timing, rate limiting, and one structured log
line per request.

The /chat route stashes its tools_called + eval scores on request.state.log_fields, so the
single log line carries them too (the brief requires every /chat eval block to be logged).
Rate limiting lives here too, so a 429 reuses the same request_id + Problem Details shape as
every other response.
"""

import hashlib
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.api.rate_limit import RateLimiter
from app.api.security import API_KEY_HEADER
from app.logging_config import get_logger
from app.models.problem import ProblemDetails

logger = get_logger("sales_agent.request")

_PROBLEM_CONTENT_TYPE = "application/problem+json"


def _client_key(request: Request) -> str:
    """Bucket callers by API key (hashed, never logged raw), falling back to client IP."""
    api_key = request.headers.get(API_KEY_HEADER)
    if api_key:
        return "key:" + hashlib.sha256(api_key.encode()).hexdigest()[:16]
    client = request.client
    return f"ip:{client.host}" if client else "ip:unknown"


def _logged_path(request: Request) -> str:
    """The matched route template (e.g. /chat/{user_id}), so a user_id — which may be a
    phone number or email — never lands in the logs. Falls back to the raw path pre-routing."""
    route = request.scope.get("route")
    return getattr(route, "path", None) or request.url.path


def _user_hash(request: Request) -> str | None:
    """A stable, non-reversible digest of the path's user_id, for correlating logs without PII."""
    user_id = (request.scope.get("path_params") or {}).get("user_id")
    return hashlib.sha256(str(user_id).encode()).hexdigest()[:12] if user_id else None


def _too_many_requests(request: Request, retry_after: float) -> JSONResponse:
    retry = max(1, int(retry_after) + 1)  # whole seconds, at least 1
    body = ProblemDetails(
        title="Too Many Requests",
        status=429,
        detail="Rate limit exceeded. Slow down and retry shortly.",
        instance=request.url.path,
        request_id=request.state.request_id,
    )
    latency_ms = int((time.perf_counter() - request.state.start) * 1000)
    logger.warning(
        "rate_limited",
        extra={
            "json_fields": {
                "event": "request",
                "method": request.method,
                "path": request.url.path,
                "status": 429,
                "request_id": request.state.request_id,
                "latency_ms": latency_ms,
            }
        },
    )
    return JSONResponse(
        status_code=429,
        content=body.model_dump(),
        media_type=_PROBLEM_CONTENT_TYPE,
        headers={"Retry-After": str(retry), "X-Request-ID": request.state.request_id},
    )


async def _request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request.state.request_id = str(uuid.uuid4())
    request.state.start = time.perf_counter()
    request.state.log_fields = {}

    # Rate limit everything except the platform health check.
    limiter: RateLimiter | None = getattr(request.app.state, "limiter", None)
    if limiter is not None and request.url.path != "/health":
        allowed, retry_after = limiter.check(_client_key(request))
        if not allowed:
            return _too_many_requests(request, retry_after)

    response = await call_next(request)

    latency_ms = int((time.perf_counter() - request.state.start) * 1000)
    response.headers["X-Request-ID"] = request.state.request_id

    fields = {
        "event": "request",
        "method": request.method,
        "path": _logged_path(request),
        "status": response.status_code,
        "request_id": request.state.request_id,
        "latency_ms": latency_ms,
    }
    if user_hash := _user_hash(request):
        fields["user_hash"] = user_hash
    fields.update(getattr(request.state, "log_fields", {}))
    logger.info("request", extra={"json_fields": fields})
    return response


def register(app: FastAPI) -> None:
    app.middleware("http")(_request_context)
