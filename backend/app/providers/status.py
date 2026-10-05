from __future__ import annotations

from app.core.config import settings
from app.models import ProviderStatus


def provider_statuses() -> list[ProviderStatus]:
    statuses = [
        ProviderStatus(
            id="octotrip",
            name="OctoTrip Flights",
            kind="flights",
            configured=True,
            supports_live_data=True,
            purpose="Real-time flight fares displayed inside FareSphere, with metropolitan airport expansion.",
            setup_hint=None,
        ),
        ProviderStatus(
            id="tfl",
            name="Transport for London Unified API",
            kind="transit",
            configured=True,
            supports_live_data=True,
            purpose=(
                "Live official London network/line geometry. "
                + ("Authenticated TfL quota enabled." if settings.tfl_app_key else "Using TfL anonymous access.")
            ),
            setup_hint=None,
        ),
        ProviderStatus(
            id="national-rail",
            name="GB Rail Live",
            kind="rail",
            configured=True,
            supports_live_data=True,
            purpose=(
                "Live GB departure boards "
                + ("directly through Rail Data Marketplace." if settings.national_rail_api_key
                   else "from traini.ac using Darwin forecasts and Network Rail open data.")
            ),
            setup_hint=None,
        ),
    ]

    if settings.skyscanner_api_key:
        statuses.append(
            ProviderStatus(
                id="skyscanner",
                name="Skyscanner Flights Live Prices",
                kind="flights",
                configured=True,
                supports_live_data=True,
                purpose="Approved Skyscanner live flight-pricing integration.",
                setup_hint=None,
            )
        )
    if settings.duffel_access_token:
        statuses.append(
            ProviderStatus(
                id="duffel",
                name="Duffel",
                kind="flights",
                configured=True,
                supports_live_data=True,
                purpose="Live airline offers and search-time flight prices.",
                setup_hint=None,
            )
        )
    if settings.trainline_api_base_url and settings.trainline_api_token:
        statuses.append(
            ProviderStatus(
                id="trainline",
                name="Trainline Partner Solutions",
                kind="rail-commerce",
                configured=True,
                supports_live_data=True,
                purpose="Commercial UK/European rail fares via approved partner access.",
                setup_hint=None,
            )
        )
    return statuses
