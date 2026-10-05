from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.models import PriceAlertRequest, SearchRequest
from app.providers.base import ProviderNotConfigured, ProviderUnavailable, UnsupportedLiveRequest
from app.providers.national_rail import NationalRailProvider
from app.providers.status import provider_statuses
from app.providers.tfl import TfLProvider
from app.services.live_search import search_live
from app.services.sample_search import PLACES, search as sample_search

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "sample_data_enabled": settings.enable_sample_data}


@router.get("/providers")
def providers():
    return provider_statuses()


@router.get("/places")
def places(q: str = ""):
    needle = q.lower().strip()
    rows = list(PLACES.values())
    if needle:
        rows = [item for item in rows if needle in item.name.lower() or needle in item.code.lower()]
    return rows


@router.post("/search")
async def journey_search(payload: SearchRequest):
    try:
        return await search_live(payload)
    except ProviderNotConfigured as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Live search is unavailable: {exc} Configure a live provider; FareSphere will not substitute sample prices.",
        ) from exc
    except UnsupportedLiveRequest as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/sample/search")
def development_sample_search(payload: SearchRequest):
    if not settings.enable_sample_data:
        raise HTTPException(status_code=404, detail="Sample data mode is disabled.")
    return sample_search(payload)


@router.get("/network/london")
async def london_network():
    try:
        return await TfLProvider().network()
    except ProviderNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/rail/departures/{crs}")
async def rail_departures(crs: str, num_rows: int = Query(default=10, ge=1, le=50)):
    try:
        return await NationalRailProvider().departures(crs, num_rows=num_rows)
    except ProviderNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/alerts")
def create_alert(payload: PriceAlertRequest):
    return {
        "id": str(uuid4()),
        "status": "prototype-only",
        "origin": payload.origin.upper(),
        "destination": payload.destination.upper(),
        "target_price": payload.target_price,
        "email": payload.email,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "note": "Persistence/background monitoring is not enabled yet; this endpoint does not claim to send alerts.",
    }
