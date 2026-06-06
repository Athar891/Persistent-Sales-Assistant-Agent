"""GET /health — build/version, uptime, and a real DB connectivity check."""

import time

from fastapi import APIRouter, Request, Response

from app.api.deps import DbDep, SettingsDep
from app.api.responses import build_meta
from app.models.envelope import Envelope
from app.models.health import HealthData

router = APIRouter(tags=["system"])


@router.get("/health", response_model=Envelope[HealthData])
async def health(
    request: Request, response: Response, db: DbDep, settings: SettingsDep
) -> Envelope[HealthData]:
    started = getattr(request.app.state, "started_at", None)
    uptime = time.time() - started if started is not None else 0.0

    try:
        await db.ping()
        database = "ok"
    except Exception:  # any driver/connection error means the dependency is down
        database = "unavailable"

    status = "ok" if database == "ok" else "degraded"
    if status != "ok":
        response.status_code = 503

    data = HealthData(
        status=status,
        version=settings.version,
        uptime_seconds=round(uptime, 3),
        database=database,
    )
    return Envelope[HealthData](data=data, meta=build_meta(request))
