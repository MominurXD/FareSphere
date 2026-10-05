from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.models import Departure, DeparturesResponse
from app.providers.base import ProviderUnavailable


class NationalRailProvider:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        api_key: str | None = None,
        endpoint_template: str | None = None,
        huxley_base_url: str | None = None,
    ):
        self._client = client
        self.api_key = settings.national_rail_api_key if api_key is None else api_key
        self.endpoint_template = (
            settings.national_rail_departures_url if endpoint_template is None else endpoint_template
        )
        self.huxley_base_url = (
            settings.huxley_base_url if huxley_base_url is None else huxley_base_url.rstrip("/")
        )

    async def departures(self, crs: str, num_rows: int = 10) -> DeparturesResponse:
        station = crs.strip().upper()
        if len(station) != 3 or not station.isalpha():
            raise ValueError("Station must be a three-letter CRS code.")

        if self.api_key:
            return await self._direct_rdm(station, num_rows)
        return await self._huxley(station, num_rows)

    async def _direct_rdm(self, station: str, num_rows: int) -> DeparturesResponse:
        url = self.endpoint_template.format(crs=station)
        payload = await self._get_json(
            url,
            headers={
                "x-apikey": self.api_key,
                "Accept": "application/json",
                "User-Agent": "FareSphere/1.0",
            },
            params={"numRows": max(1, min(num_rows, 50)), "timeWindow": 120},
            source="National Rail",
        )
        return self._parse(
            payload,
            station,
            "National Rail Darwin / Rail Data Marketplace",
        )

    async def _huxley(self, station: str, num_rows: int) -> DeparturesResponse:
        url = f"{self.huxley_base_url}/departures/{station}/{max(1, min(num_rows, 50))}"
        payload = await self._get_json(
            url,
            headers={"Accept": "application/json", "User-Agent": "FareSphere/1.0"},
            params={"expand": "false"},
            source="Huxley 2",
        )
        return self._parse(
            payload,
            station,
            "National Rail Darwin via Huxley 2 Community Edition",
        )

    async def _get_json(self, url: str, headers: dict, params: dict, source: str) -> dict:
        owns = self._client is None
        client = self._client or httpx.AsyncClient(timeout=25.0)
        try:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise ProviderUnavailable(
                f"{source} live departures returned HTTP {exc.response.status_code}."
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailable(f"{source} live departures failed: {exc}") from exc
        finally:
            if owns:
                await client.aclose()

    def _parse(self, payload: dict, station: str, provider: str) -> DeparturesResponse:
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
            provider=provider,
            station=payload.get("crs") or station,
            generated_at=datetime.now(timezone.utc),
            departures=departures,
        )
