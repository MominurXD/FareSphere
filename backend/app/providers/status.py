from __future__ import annotations

from app.core.config import settings
from app.models import ProviderStatus


def provider_statuses() -> list[ProviderStatus]:
    return [
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
            configured=bool(settings.tfl_app_key),
            supports_live_data=True,
            purpose="Current London rail/transit lines and stop geometry.",
            setup_hint=None if settings.tfl_app_key else "Set TFL_APP_KEY on the backend.",
        ),
        ProviderStatus(
            id="national-rail",
            name="National Rail Darwin / Rail Data Marketplace",
            kind="rail",
            configured=bool(settings.national_rail_api_key and settings.national_rail_departures_url),
            supports_live_data=True,
            purpose="Live GB rail departures, expected times, platforms and cancellations.",
            setup_hint=(
                None
                if settings.national_rail_api_key and settings.national_rail_departures_url
                else "Subscribe to Live Departure Board in Rail Data Marketplace and set NATIONAL_RAIL_API_KEY and NATIONAL_RAIL_DEPARTURES_URL."
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
