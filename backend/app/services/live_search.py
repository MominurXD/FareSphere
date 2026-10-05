from __future__ import annotations

import asyncio

from app.core.config import settings
from app.models import SearchRequest, SearchResponse
from app.providers.base import UnsupportedLiveRequest
from app.providers.duffel import DuffelProvider
from app.providers.national_rail import NationalRailProvider
from app.providers.octotrip import OctoTripProvider
from app.providers.skyscanner import SkyscannerProvider
from app.providers.tfl_journey import TfLJourneyProvider, is_london_ground_journey


async def search_live(request: SearchRequest) -> SearchResponse:
    origin = request.origin.strip()
    destination = request.destination.strip()
    origin_upper = origin.upper()
    destination_upper = destination.upper()

    if origin_upper == destination_upper:
        raise UnsupportedLiveRequest("Origin and destination must be different.")

    # London city/airport journeys belong on the ground network.
    if is_london_ground_journey(origin_upper, destination_upper):
        return await TfLJourneyProvider().search(request)

    # Auto-detect GB rail: exact 3-letter CRS codes count as rail; longer
    # names/groups are also resolved by traini.ac. This avoids treating LON
    # (a flight city code) as a rail group while still allowing EUS -> MAN.
    rail = NationalRailProvider()
    origin_is_rail, destination_is_rail = await asyncio.gather(
        rail.resolves_as_rail(origin),
        rail.resolves_as_rail(destination),
    )
    if origin_is_rail and destination_is_rail:
        return await rail.journeys(request)

    # A non-rail route must be expressed as IATA codes for the flight provider.
    if len(origin_upper) != 3 or len(destination_upper) != 3:
        raise UnsupportedLiveRequest(
            "Flight searches need three-letter IATA codes. For UK rail you can use a CRS code "
            "or select a station suggestion."
        )

    if settings.skyscanner_api_key:
        return await SkyscannerProvider().search(request)
    if settings.duffel_access_token:
        return await DuffelProvider().search(request)
    return await OctoTripProvider().search(request)
