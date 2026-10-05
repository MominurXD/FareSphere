from __future__ import annotations

import asyncio

from app.core.config import settings
from app.models import SearchRequest, SearchResponse
from app.providers.base import UnsupportedLiveRequest
from app.providers.duffel import DuffelProvider
from app.providers.national_rail import NationalRailProvider
from app.providers.octotrip import OctoTripProvider
from app.providers.skyscanner import SkyscannerProvider
from app.providers.tfl_journey import (
    LONDON_PLACES,
    TfLJourneyProvider,
    is_london_ground_journey,
)


def _resolved_rail_station(result: dict, query: str) -> dict | None:
    resolved = result.get("resolved")
    if not isinstance(resolved, dict):
        return None

    cleaned = query.strip()
    if len(cleaned) == 3 and cleaned.isalpha():
        if (
            resolved.get("type") == "station"
            and str(resolved.get("crs") or "").upper() == cleaned.upper()
        ):
            return resolved
        return None

    return resolved if resolved.get("type") == "station" else None


def _is_rail_resolution(result: dict, query: str) -> bool:
    resolved = result.get("resolved")
    if not isinstance(resolved, dict):
        return False

    cleaned = query.strip()
    if len(cleaned) == 3 and cleaned.isalpha():
        return (
            resolved.get("type") == "station"
            and str(resolved.get("crs") or "").upper() == cleaned.upper()
        )
    return resolved.get("type") in {"station", "group"}


async def search_live(request: SearchRequest) -> SearchResponse:
    origin = request.origin.strip()
    destination = request.destination.strip()
    origin_upper = origin.upper()
    destination_upper = destination.upper()

    if origin_upper == destination_upper:
        raise UnsupportedLiveRequest("Origin and destination must be different.")

    # Known London city/airport pairs go straight to TfL.
    if is_london_ground_journey(origin_upper, destination_upper):
        return await TfLJourneyProvider().search(request)

    rail = NationalRailProvider()
    origin_lookup, destination_lookup = await asyncio.gather(
        rail.station_search(origin),
        rail.station_search(destination),
    )
    origin_is_rail = _is_rail_resolution(origin_lookup, origin)
    destination_is_rail = _is_rail_resolution(destination_lookup, destination)
    origin_station = _resolved_rail_station(origin_lookup, origin)
    destination_station = _resolved_rail_station(destination_lookup, destination)

    # A London city/airport code plus a London rail station is still a ground
    # journey. Resolve the rail station through TfL StopPoint Search and use
    # Journey Planner instead of sending nonsense routes such as LHR -> PAD
    # to the flight API.
    tfl = TfLJourneyProvider()
    if origin_upper in LONDON_PLACES and destination_station is not None:
        destination_place = await tfl.resolve_london_rail_station(destination_station)
        if destination_place is not None:
            return await tfl.search(request, destination_override=destination_place)

    if destination_upper in LONDON_PLACES and origin_station is not None:
        origin_place = await tfl.resolve_london_rail_station(origin_station)
        if origin_place is not None:
            return await tfl.search(request, origin_override=origin_place)

    # Two resolved GB rail endpoints use the live rail journey provider.
    if origin_is_rail and destination_is_rail:
        return await rail.journeys(request)

    # Remaining routes are flights and must be IATA-style 3-letter codes.
    if len(origin_upper) != 3 or len(destination_upper) != 3:
        raise UnsupportedLiveRequest(
            "Flight searches need three-letter IATA codes. For UK rail, select a station suggestion "
            "or enter a CRS code/station name."
        )

    if settings.skyscanner_api_key:
        return await SkyscannerProvider().search(request)
    if settings.duffel_access_token:
        return await DuffelProvider().search(request)
    return await OctoTripProvider().search(request)
