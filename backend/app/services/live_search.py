from __future__ import annotations

from app.core.config import settings
from app.models import SearchRequest, SearchResponse
from app.providers.duffel import DuffelProvider
from app.providers.octotrip import OctoTripProvider
from app.providers.skyscanner import SkyscannerProvider
from app.providers.tfl_journey import TfLJourneyProvider, is_london_ground_journey


async def search_live(request: SearchRequest) -> SearchResponse:
    origin = request.origin.upper()
    destination = request.destination.upper()

    # A city-to-airport journey such as LON -> LHR is ground transport, not a
    # flight. Route it through TfL first so FareSphere returns usable options
    # and quoted fares instead of trying LHR -> LHR / LGW -> LHR flights.
    if is_london_ground_journey(origin, destination):
        return await TfLJourneyProvider().search(request)

    if origin == destination:
        from app.providers.base import UnsupportedLiveRequest
        raise UnsupportedLiveRequest("Origin and destination must be different.")

    # Use configured commercial providers when the owner explicitly adds one.
    # Otherwise OctoTrip provides real-time in-app flight fares with no API key.
    if settings.skyscanner_api_key:
        return await SkyscannerProvider().search(request)
    if settings.duffel_access_token:
        return await DuffelProvider().search(request)
    return await OctoTripProvider().search(request)
