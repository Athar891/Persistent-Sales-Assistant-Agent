"""One global exception surface, rendered as RFC 9457 Problem Details.

Every error — domain, HTTP, validation, or unhandled — becomes an
`application/problem+json` body carrying the request_id. No stack traces leak.
"""

from http import HTTPStatus
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.errors import AgentError
from app.logging_config import get_logger
from app.models.problem import ProblemDetails

PROBLEM_CONTENT_TYPE = "application/problem+json"
logger = get_logger("sales_agent.error")


def _problem(request: Request, *, status: int, title: str, detail: str) -> JSONResponse:
    body = ProblemDetails(
        title=title,
        status=status,
        detail=detail,
        instance=request.url.path,
        request_id=getattr(request.state, "request_id", None),
    )
    return JSONResponse(
        status_code=status, content=body.model_dump(), media_type=PROBLEM_CONTENT_TYPE
    )


async def _handle_agent_error(request: Request, exc: Exception) -> JSONResponse:
    err = cast(AgentError, exc)
    return _problem(request, status=err.status, title=err.title, detail=str(err) or err.title)


async def _handle_http_error(request: Request, exc: Exception) -> JSONResponse:
    err = cast(StarletteHTTPException, exc)
    title = HTTPStatus(err.status_code).phrase
    return _problem(request, status=err.status_code, title=title, detail=str(err.detail))


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    err = cast(RequestValidationError, exc)
    detail = "; ".join(
        f"{'.'.join(str(p) for p in e.get('loc', []))}: {e.get('msg', '')}".strip(": ")
        for e in err.errors()
    )
    return _problem(
        request, status=422, title="Unprocessable Entity", detail=detail or "Validation failed."
    )


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    # Log the real error server-side; never leak it to the client.
    logger.error(
        "unhandled_exception",
        exc_info=exc,
        extra={"json_fields": {"request_id": getattr(request.state, "request_id", None)}},
    )
    return _problem(
        request,
        status=500,
        title="Internal Server Error",
        detail="An unexpected error occurred.",
    )


def register(app: FastAPI) -> None:
    app.add_exception_handler(AgentError, _handle_agent_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
    app.add_exception_handler(Exception, _handle_unexpected)
