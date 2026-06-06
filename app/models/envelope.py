"""The consistent response envelope every successful endpoint returns.

`data` carries the endpoint-specific payload; `meta` carries cross-cutting request
metadata. The /chat `data` keeps exactly the brief's response/eval/tools_called/
session_id contract — the envelope wraps around it, it does not replace it.
"""

from datetime import datetime

from pydantic import BaseModel


class Meta(BaseModel):
    request_id: str
    session_id: str | None = None
    timestamp: datetime
    latency_ms: int


class Envelope[T](BaseModel):
    data: T
    meta: Meta
