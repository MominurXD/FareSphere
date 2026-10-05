from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.models import Departure, DeparturesResponse
from app.providers.base import ProviderNotConfigured, ProviderUnavailable


class NationalRailProvider:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        api_key: str | None = None,
        endpoint_template: str | None = None,
    ):
        self._client = client
        self.api_key = settings.national_rail_api_key if api_key is None else api_key
        self.endpoint_template = (
            settings.national_rail_departures_url if endpoint_template is None else endpoint_template
        )

    async def departures(self, crs: str, num_rows: int = 10) -> DeparturesResponse:
        # RDM's public Live Departure Board product is open data, but the
        # marketplace still issues each subscriber a consumer key.
        if not self.api_key:
            raise ProviderNotConfigured(
                "National Rail needs a free Rail Data Marketplace Live Departure Board consumer key."
            )

        station = crs.strip().upper()
        if len(station) != 3 or not station.isalpha():
            raise ValueError("Station must be a three-letter CRS code.")

        url = self.endpoint_template.format(crs=station)
        owns = self._client is None
        client = self._client or httpx.AsyncClient(timeout=20.0)
        try:
            response = await client.get(
                url,
                headers={
                    "x-apikey": self.api_key,
                    "Accept": "application/json",
                    "User-Agent": "FareSphere/1.0",
                },
                params={"numRows": max(1, min(num_rows, 50)), "timeWindow": 120},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            detail = f"National Rail returned HTTP {exc.response.status_code}."
            if exc.response.status_code in {401, 403}:
                detail += " Check that the RDM consumer key is subscribed to the Live Departure Board product."
            raise ProviderUnavailable(detail) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"National Rail request failed: {exc}") from exc
        finally:
            if owns:
                await client.aclose()

        raw_services = payload.get("trainServices") or payload.get("services") or []
        if isinstance(raw_services, dict):
            raw_services = raw_services.get("service") or raw_services.get("trainService") or []
        if isinstance(raw_services, dict):
            raw_services = [raw_services]

        departures: list[Departure] = []
        for service in raw_services:
            destination = service.get("destination") or service.get("destinations") or []
            if isinstance(destination, list) and destination:
                first = destination[0]
                destination_name = first.get("locationName") if isinstance(first, dict) else str(first)
            elif isinstance(destination, dict):
                destination_name = destination.get("locationName") or destination.get("name") or "Unknown"
            else:
                destination_name = str(destination or "Unknown")

            expected = service.get("etd") or service.get("expectedDeparture")
            cancelled = bool(service.get("isCancelled")) or str(expected).lower() == "cancelled"
            departures.append(
                Departure(
                    service_id=service.get("serviceID") or service.get("serviceId"),
                    operator=service.get("operator"),
                    destination=destination_name,
                    scheduled=service.get("std") or service.get("scheduledDeparture"),
                    expected=expected,
                    platform=service.get("platform"),
                    cancelled=cancelled,
                )
            )

        return DeparturesResponse(
            provider="National Rail Darwin / Rail Data Marketplace",
            station=station,
            generated_at=datetime.now(timezone.utc),
            departures=departures,
        )
