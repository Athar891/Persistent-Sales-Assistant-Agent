"""GET /catalog — the product/pricing catalog the agent uses."""

from fastapi import APIRouter, Request

from app.api.deps import CatalogDep
from app.api.responses import build_meta
from app.models.catalog import Catalog
from app.models.envelope import Envelope

router = APIRouter(tags=["catalog"])


@router.get("/catalog", response_model=Envelope[Catalog])
async def get_catalog(request: Request, catalog: CatalogDep) -> Envelope[Catalog]:
    return Envelope[Catalog](data=Catalog(plans=catalog.get_all()), meta=build_meta(request))
