from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx

from app.core.config import settings
from app.models import Departure, DeparturesResponse, Journey, Leg, Place, SearchRequest, SearchResponse
from app.providers.base import ProviderUnavailable, UnsupportedLiveRequest


class NationalRailProvider:
    """GB rail integration.

    Direct RDM access is used for the departure board when the owner supplies
    a National Rail key. Otherwise FareSphere uses traini.ac's public v1 JSON
    API for live journey/departure data in this personal portfolio project.
    """

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        api_key: str | None = None,
        endpoint_template: str | None = None,
        trainiac_base_url: str | None = None,
    ):
        self._client = client
        self.api_key = settings.national_rail_api_key if api_key is None else api_key
        self.endpoint_template = (
            settings.national_rail_departures_url if endpoint_template is None else endpoint_template
        )
        self.trainiac_base_url = (
            settings.trainiac_base_url if trainiac_base_url is None else trainiac_base_url.rstrip("/")
        )

    async def station_search(self, query: str) -> dict:
        query = query.strip()
        if len(query) < 2:
            return {"query": query, "resolved": None, "results": []}
        payload = await self._trainiac_get(
            "/v1/stations",
            params={"q": query},
            purpose="station search",
        )
        data = self._unwrap(payload, "station search")
        matches = [
            {
                "crs": item.get("crs"),
                "name": item.get("name"),
                "type": item.get("type"),
                "calls_today": item.get("calls_today"),
            }
            for item in (data.get("matches") or [])
            if item.get("type") == "station" and item.get("crs")
        ]
        return {
            "query": query,
            "resolved": data.get("resolves_to"),
            "near_misses": bool(data.get("near_misses")),
            "results": matches[:12],
        }

    async def resolves_as_rail(self, query: str) -> bool:
        result = await self.station_search(query)
        resolved = result.get("resolved")
        if not isinstance(resolved, dict):
            return False

        cleaned = query.strip()
        # Three-letter inputs are ambiguous with airport IATA codes. Only call
        # them rail when traini.ac resolves the exact same CRS code.
        if len(cleaned) == 3 and cleaned.isalpha():
            return (
                resolved.get("type") == "station"
                and str(resolved.get("crs") or "").upper() == cleaned.upper()
            )

        return resolved.get("type") in {"station", "group"}

    async def journeys(self, request: SearchRequest, limit: int = 10) -> SearchResponse:
        london_today = datetime.now(ZoneInfo("Europe/London")).date()
        if request.departure_date != london_today:
            raise UnsupportedLiveRequest(
                "Live GB rail routing currently covers today's services. "
                "Future dated National Rail journey planning/fare pricing requires a licensed OJP/fare provider."
            )

        origin_query = request.origin.strip()
        destination_query = request.destination.strip()
        payload = await self._trainiac_get(
            f"/v1/journey/{quote(origin_query, safe='')}/{quote(destination_query, safe='')}",
            params={
                "limit": max(1, min(limit, 20)),
                "max_changes": 2,
                "min_interchange_min": 5,
                "from_time": request.departure_time,
            },
            purpose="journey planning",
        )
        data = self._unwrap(payload, "journey planning")
        if not isinstance(data, list) or not data:
            raise ProviderUnavailable("No live GB rail journeys were returned for this route/time.")

        journeys: list[Journey] = []
        for item in data:
            journey_type = item.get("type")
            raw_legs = [item.get("leg")] if journey_type == "direct" else (item.get("legs") or [])
            raw_legs = [leg for leg in raw_legs if isinstance(leg, dict)]
            if not raw_legs:
                continue

            connections = item.get("connections") or []
            connection_at_risk = any(
                isinstance(connection, dict) and connection.get("outlook") == "at_risk"
                for connection in connections
            )

            legs: list[Leg] = []
            operator_names: list[str] = []
            for raw_leg in raw_legs:
                train = raw_leg.get("train") or {}
                operator = train.get("operator") or {}
                carrier = operator.get("name") or operator.get("code") or "National Rail"
                if carrier not in operator_names:
                    operator_names.append(carrier)

                origin = self._place(raw_leg.get("from"), fallback=origin_query)
                destination = self._place(raw_leg.get("to"), fallback=destination_query)
                depart_at = self._time_at(raw_leg.get("departs"))
                arrive_at = self._time_at(raw_leg.get("arrives"))
                platform = self._platform(raw_leg.get("departure_platform"))
                status = self._status(raw_leg.get("departs"))

                legs.append(
                    Leg(
                        mode="train",
                        carrier=carrier,
                        number=train.get("headcode"),
                        origin=origin,
                        destination=destination,
                        depart_at=depart_at,
                        arrive_at=arrive_at,
                        ticket_price=None,
                        currency="GBP",
                        price_verified=False,
                        source="traini.ac live GB rail data",
                        status=status,
                        platform=platform,
                    )
                )

            if not legs:
                continue

            changes = max(0, len(legs) - 1)
            badges = [
                "Live GB rail",
                "Direct" if changes == 0 else f"{changes} change" + ("s" if changes != 1 else ""),
                "Fare not supplied",
            ]
            if connection_at_risk:
                badges.append("Connection at risk")

            risk_score = min(80, 6 + changes * 10 + (20 if connection_at_risk else 0))
            journeys.append(
                Journey(
                    id=str(uuid4()),
                    label=" + ".join(operator_names) or "National Rail",
                    legs=legs,
                    total_price=None,
                    currency="GBP",
                    total_duration_minutes=int(item.get("duration_minutes") or 1),
                    total_emissions_kg=None,
                    risk_score=risk_score,
                    savings_vs_baseline=None,
                    badges=badges,
                    score=float(item.get("duration_minutes") or 1),
                    price_verified=False,
                    source="traini.ac — Network Rail open data + National Rail Darwin forecasts",
                )
            )

        if not journeys:
            raise ProviderUnavailable("Live GB rail data was returned, but no usable passenger journey could be parsed.")

        # traini.ac does not provide fares. Never pretend "cheapest" can rank
        # prices when the source has no price field.
        journeys.sort(key=lambda item: (item.total_duration_minutes, item.risk_score))

        return SearchResponse(
            origin=journeys[0].legs[0].origin,
            destination=journeys[0].legs[-1].destination,
            baseline_price=None,
            currency="GBP",
            results=journeys,
            flexible_date_savings=[],
            generated_at=datetime.now(timezone.utc),
            data_mode="live",
            providers_used=["GB Rail Live (traini.ac)"],
            notice=(
                "Live route, delay, platform and connection data are shown inside FareSphere. "
                "This public rail source does not provide ticket fares, so FareSphere shows 'Fare unavailable' "
                "instead of inventing a rail price. A licensed National Rail OJP/rail-fare provider is required "
                "for future-date journey planning and ticket prices."
            ),
        )

    async def departures(self, crs: str, num_rows: int = 10) -> DeparturesResponse:
        station = crs.strip().upper()
        if len(station) != 3 or not station.isalpha():
            raise ValueError("Station must be a three-letter CRS code.")

        if self.api_key:
            return await self._direct_rdm(station, num_rows)
        return await self._trainiac_departures(station, num_rows)

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
        return self._parse_rdm(payload, station, "National Rail Darwin / Rail Data Marketplace")

    async def _trainiac_departures(self, station: str, num_rows: int) -> DeparturesResponse:
        payload = await self._trainiac_get(
            f"/v1/departures/{station}",
            params={"limit": max(1, min(num_rows, 50))},
            purpose="departure board",
        )
        data = self._unwrap(payload, "departure board")
        request = payload.get("request") or {}
        station_arg = request.get("station") or {}
        resolution = station_arg.get("resolution") or {}
        resolved_crs = resolution.get("crs") if resolution.get("type") == "station" else station

        departures: list[Departure] = []
        for service in data if isinstance(data, list) else []:
            destination = service.get("destination") or {}
            departs = service.get("departs") or {}
            train = service.get("train") or {}
            operator = train.get("operator") or {}
            departures.append(
                Departure(
                    service_id=train.get("id") or train.get("uid") or train.get("headcode"),
                    operator=operator.get("name") or operator.get("code"),
                    destination=destination.get("name") or "Unknown",
                    scheduled=self._clock(departs.get("scheduled")),
                    expected=self._clock(self._estimate_at(departs)),
                    platform=self._platform(service.get("platform")),
                    cancelled=(departs.get("estimate") or {}).get("type") == "cancelled",
                )
            )

        return DeparturesResponse(
            provider="traini.ac — Network Rail open data + National Rail Darwin",
            station=resolved_crs or station,
            generated_at=datetime.now(timezone.utc),
            departures=departures,
        )

    async def _trainiac_get(self, path: str, params: dict, purpose: str) -> dict:
        return await self._get_json(
            f"{self.trainiac_base_url}{path}",
            headers={"Accept": "application/json", "User-Agent": "FareSphere/1.0 (personal portfolio)"},
            params=params,
            source=f"traini.ac {purpose}",
        )

    async def _get_json(self, url: str, headers: dict, params: dict, source: str) -> dict:
        owns = self._client is None
        client = self._client or httpx.AsyncClient(timeout=25.0)
        try:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            message = f"{source} returned HTTP {exc.response.status_code}."
            try:
                body = exc.response.json()
                error = body.get("error") if isinstance(body, dict) else None
                if isinstance(error, dict) and error.get("message"):
                    message += f" {error['message']}"
                elif error:
                    message += f" {error}"
            except ValueError:
                pass
            raise ProviderUnavailable(message) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailable(f"{source} failed: {exc}") from exc
        finally:
            if owns:
                await client.aclose()

    @staticmethod
    def _unwrap(payload: dict, purpose: str):
        if payload.get("type") == "error":
            error = payload.get("error") or {}
            raise ProviderUnavailable(error.get("message") or f"traini.ac {purpose} failed.")
        if payload.get("type") != "ok":
            raise ProviderUnavailable(f"traini.ac {purpose} returned an unexpected response.")
        return payload.get("data")

    @staticmethod
    def _estimate_at(time_value: dict | None) -> str | None:
        time_value = time_value or {}
        estimate = time_value.get("estimate") or {}
        if estimate.get("type") in {"actual", "forecast"}:
            return estimate.get("at")
        return time_value.get("scheduled")

    @classmethod
    def _time_at(cls, time_value: dict | None) -> datetime:
        value = cls._estimate_at(time_value)
        if not value:
            raise ProviderUnavailable("Live rail journey contained a leg without a usable time.")
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    @staticmethod
    def _clock(value: str | None) -> str | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%H:%M")
        except ValueError:
            return value

    @staticmethod
    def _platform(platform: dict | None) -> str | None:
        platform = platform or {}
        return str(platform.get("number")) if platform.get("type") == "known" and platform.get("number") else None

    @classmethod
    def _status(cls, time_value: dict | None) -> str | None:
        time_value = time_value or {}
        estimate = time_value.get("estimate") or {}
        estimate_type = estimate.get("type")
        if estimate_type == "cancelled":
            return "Cancelled"
        if estimate_type == "delayed_no_estimate":
            return "Delayed"
        if estimate_type in {"forecast", "actual"} and estimate.get("at"):
            label = "Expected" if estimate_type == "forecast" else "Actual"
            delay = time_value.get("delay_minutes")
            suffix = f" ({delay:+}m)" if isinstance(delay, int) and delay else ""
            return f"{label} {cls._clock(estimate['at'])}{suffix}"
        return None

    @staticmethod
    def _place(raw: dict | None, fallback: str) -> Place:
        raw = raw or {}
        name = raw.get("name") or fallback
        code = raw.get("crs")
        if not code:
            letters = "".join(ch for ch in str(name).upper() if ch.isalnum())
            code = letters[:3] or "NR"
        return Place(
            code=str(code),
            name=str(name),
            country="GB",
            kind="station",
        )

    def _parse_rdm(self, payload: dict, station: str, provider: str) -> DeparturesResponse:
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
