"""Request-context middleware: request_id, timing, and one structured log line per request.

The /chat route stashes its tools_called + eval scores on request.state.log_fields, so the
single log line carries them too (the brief requires every /chat eval block to be logged).
"""

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from app.logging_config import get_logger

logger = get_logger("sales_agent.request")


async def _request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request.state.request_id = str(uuid.uuid4())
    request.state.start = time.perf_counter()
    request.state.log_fields = {}

    response = await call_next(request)

    latency_ms = int((time.perf_counter() - request.state.start) * 1000)
    response.headers["X-Request-ID"] = request.state.request_id

    fields = {
        "event": "request",
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "request_id": request.state.request_id,
        "latency_ms": latency_ms,
    }
    fields.update(getattr(request.state, "log_fields", {}))
    logger.info("request", extra={"json_fields": fields})
    return response


def register(app: FastAPI) -> None:
    app.middleware("http")(_request_context)
