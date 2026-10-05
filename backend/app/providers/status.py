from __future__ import annotations

from app.core.config import settings
from app.models import ProviderStatus


def provider_statuses() -> list[ProviderStatus]:
    return [
        ProviderStatus(
            id="skyscanner",
            name="Skyscanner Flights Live Prices",
            kind="flights",
            configured=bool(settings.skyscanner_api_key),
            supports_live_data=True,
            purpose="Real-time flight prices across Skyscanner supply partners.",
            setup_hint=None if settings.skyscanner_api_key else "Set SKYSCANNER_API_KEY from an approved Skyscanner partner account.",
        ),
        ProviderStatus(
            id="duffel",
            name="Duffel",
            kind="flights",
            configured=bool(settings.duffel_access_token),
            supports_live_data=True,
            purpose="Live airline offers and search-time flight prices.",
            setup_hint=None if settings.duffel_access_token else "Set DUFFEL_ACCESS_TOKEN on the backend.",
        ),
        ProviderStatus(
            id="tfl",
            name="Transport for London Unified API",
            kind="transit",
            configured=True,
            supports_live_data=True,
            purpose=(
                "Live official London network/line geometry. "
                + ("Authenticated TfL quota enabled." if settings.tfl_app_key else "Using TfL anonymous access (50 requests/minute limit).")
            ),
            setup_hint=None if settings.tfl_app_key else "Optional: set TFL_APP_KEY for a higher subscribed TfL request quota.",
        ),
        ProviderStatus(
            id="national-rail",
            name="National Rail Darwin / Rail Data Marketplace",
            kind="rail",
            configured=bool(settings.national_rail_api_key),
            supports_live_data=True,
            purpose="Live GB rail departures, expected times, platforms and cancellations.",
            setup_hint=(
                None
                if settings.national_rail_api_key
                else "Add the free Live Departure Board consumer key as NATIONAL_RAIL_API_KEY."
            ),
        ),
        ProviderStatus(
            id="trainline",
            name="Trainline Partner Solutions",
            kind="rail-commerce",
            configured=bool(settings.trainline_api_base_url and settings.trainline_api_token),
            supports_live_data=True,
            purpose="Commercial UK/European rail search and fares when partner access is approved.",
            setup_hint=(
                None
                if settings.trainline_api_base_url and settings.trainline_api_token
                else "Requires a Trainline Partner Solutions distribution agreement / Global API access."
            ),
        ),
    ]
