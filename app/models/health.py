"""Health-check payload."""

from pydantic import BaseModel


class HealthData(BaseModel):
    status: str  # "ok" | "degraded"
    version: str
    uptime_seconds: float
    database: str  # "ok" | "unavailable"
