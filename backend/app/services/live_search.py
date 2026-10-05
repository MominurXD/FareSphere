from __future__ import annotations

from app.core.config import settings
from app.models import SearchRequest, SearchResponse
from app.providers.base import ProviderNotConfigured
from app.providers.duffel import DuffelProvider
from app.providers.skyscanner import SkyscannerProvider


async def search_live(request: SearchRequest) -> SearchResponse:
    # Prefer Skyscanner when approved partner access is configured; otherwise
    # use Duffel. Never substitute sample data for a missing live provider.
    if settings.skyscanner_api_key:
        return await SkyscannerProvider().search(request)
    if settings.duffel_access_token:
        return await DuffelProvider().search(request)
    raise ProviderNotConfigured(
        "No live flight-pricing credential is configured. Add SKYSCANNER_API_KEY or DUFFEL_ACCESS_TOKEN."
    )
