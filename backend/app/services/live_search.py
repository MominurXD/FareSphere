from __future__ import annotations

from app.models import SearchRequest, SearchResponse
from app.providers.duffel import DuffelProvider


async def search_live(request: SearchRequest) -> SearchResponse:
    # Current production search uses verified live flight offers. Rail fare search is
    # intentionally not merged until an approved commerce provider is configured.
    return await DuffelProvider().search(request)
