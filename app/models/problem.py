"""RFC 9457 Problem Details — the single error shape for the whole API.

Served as `application/problem+json`. `request_id` is our extension member so a
client can quote it back when reporting a failure.
"""

from pydantic import BaseModel


class ProblemDetails(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    request_id: str | None = None
