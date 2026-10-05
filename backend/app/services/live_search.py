from __future__ import annotations

from app.core.config import settings
from app.models import SearchRequest, SearchResponse
from app.providers.duffel import DuffelProvider
from app.providers.octotrip import OctoTripProvider
from app.providers.skyscanner import SkyscannerProvider


async def search_live(request: SearchRequest) -> SearchResponse:
    # Use configured commercial providers when the owner explicitly adds one.
    # Otherwise OctoTrip provides real-time in-app fares with no API key.
    if settings.skyscanner_api_key:
        return await SkyscannerProvider().search(request)
    if settings.duffel_access_token:
        return await DuffelProvider().search(request)
    return await OctoTripProvider().search(request)
