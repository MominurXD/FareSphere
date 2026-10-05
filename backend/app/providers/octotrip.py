from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from app.models import Journey, Leg, Place, SearchRequest, SearchResponse
from app.providers.base import ProviderUnavailable, UnsupportedLiveRequest


OCTOTRIP_MCP = "https://mcp.octotrip.app/flights/mcp"

# Metropolitan IATA codes are useful in the FareSphere UI, but some live
# suppliers only return inventory for concrete airports. Expand the common
# metro codes and merge the live results back into one list.
AIRPORT_GROUPS: dict[str, list[str]] = {
    "LON": ["LHR", "LGW", "STN", "LTN", "LCY"],
    "PAR": ["CDG", "ORY", "BVA"],
    "ROM": ["FCO", "CIA"],
    "MIL": ["MXP", "LIN", "BGY"],
    "NYC": ["JFK", "EWR", "LGA"],
    "TYO": ["HND", "NRT"],
    "CHI": ["ORD", "MDW"],
    "WAS": ["IAD", "DCA", "BWI"],
    "BUE": ["EZE", "AEP"],
    "RIO": ["GIG", "SDU"],
    "SAO": ["GRU", "CGH", "VCP"],
}


def _parse_datetime(date_value: str | None, time_value: str | None) -> datetime:
    if not date_value:
        raise ValueError("Missing flight date.")
    value = f"{date_value}T{time_value or '00:00'}"
    return datetime.fromisoformat(value)


def _extract_mcp_payload(response: httpx.Response) -> dict:
    content_type = response.headers.get("content-type", "")
    messages: list[dict] = []

    if "application/json" in content_type:
        messages.append(response.json())
    else:
        for line in response.text.splitlines():
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            try:
                messages.append(json.loads(raw))
            except json.JSONDecodeError:
                continue

    for message in reversed(messages):
        if message.get("error"):
            detail = message["error"].get("message") or "OctoTrip returned an MCP error."
            raise ProviderUnavailable(detail)

        result = message.get("result") or {}
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            return structured

        for item in result.get("content") or []:
            if item.get("type") != "text":
                continue
            text = item.get("text") or ""
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed

    raise ProviderUnavailable("OctoTrip returned no usable flight-search payload.")


def _place(code: str, resolved: dict | None = None) -> Place:
    resolved = resolved or {}
    return Place(
        code=code,
        name=resolved.get("name") or code,
        country=resolved.get("country_code") or "Unknown",
        lat=None,
        lon=None,
        kind="airport",
    )


class OctoTripProvider:
    name = "OctoTrip Flights"

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client

    @staticmethod
    def _pairs(origin: str, destination: str) -> list[tuple[str, str]]:
        origins = AIRPORT_GROUPS.get(origin, [origin])
        destinations = AIRPORT_GROUPS.get(destination, [destination])

        if len(origins) == 1 and len(destinations) == 1:
            return [(origins[0], destinations[0])]

        pairs: list[tuple[str, str]] = []
        if len(destinations) == 1:
            pairs = [(airport, destinations[0]) for airport in origins]
        elif len(origins) == 1:
            pairs = [(origins[0], airport) for airport in destinations]
        else:
            # Keep within OctoTrip's documented burst capacity.
            for origin_airport in origins:
                for destination_airport in destinations:
                    pairs.append((origin_airport, destination_airport))
                    if len(pairs) == 5:
                        return pairs
        return pairs[:5]

    async def search(self, request: SearchRequest) -> SearchResponse:
        if request.checked_bags:
            raise UnsupportedLiveRequest(
                "FareSphere does not add guessed checked-bag charges. Search with checked_bags=0."
            )
        if request.flexible_days:
            raise UnsupportedLiveRequest(
                "Flexible-date pricing is not enabled for this live provider. Set flexible_days=0."
            )

        pairs = self._pairs(request.origin.upper(), request.destination.upper())
        owns = self._client is None
        client = self._client or httpx.AsyncClient(timeout=45.0)

        try:
            outcomes = await asyncio.gather(
                *(self._search_pair(client, request, origin, destination) for origin, destination in pairs),
                return_exceptions=True,
            )
        finally:
            if owns:
                await client.aclose()

        journeys: list[Journey] = []
        errors: list[str] = []
        for outcome in outcomes:
            if isinstance(outcome, Exception):
                errors.append(str(outcome))
                continue
            journeys.extend(outcome)

        # Remove duplicate booking results occasionally returned across metro-airport queries.
        deduped: dict[tuple, Journey] = {}
        for journey in journeys:
            first = journey.legs[0]
            last = journey.legs[-1]
            key = (
                first.origin.code,
                last.destination.code,
                first.depart_at.isoformat(),
                journey.label,
                round(journey.total_price, 2),
            )
            current = deduped.get(key)
            if current is None or journey.total_duration_minutes < current.total_duration_minutes:
                deduped[key] = journey
        journeys = list(deduped.values())

        if not journeys:
            expanded = ", ".join(f"{a}→{b}" for a, b in pairs)
            detail = f"No live fares were returned after checking {expanded}."
            if errors:
                detail += f" Provider detail: {errors[0]}"
            raise ProviderUnavailable(detail)

        if request.sort == "fastest":
            journeys.sort(key=lambda item: (item.total_duration_minutes, item.total_price))
        elif request.sort == "best":
            cheapest = min(item.total_price for item in journeys) or 1.0
            fastest = min(item.total_duration_minutes for item in journeys) or 1
            for item in journeys:
                item.score = round(
                    (item.total_price / cheapest) * 0.65
                    + (item.total_duration_minutes / fastest) * 0.35,
                    4,
                )
            journeys.sort(key=lambda item: item.score)
        else:
            journeys.sort(key=lambda item: (item.total_price, item.total_duration_minutes))

        return SearchResponse(
            origin=journeys[0].legs[0].origin,
            destination=journeys[0].legs[-1].destination,
            baseline_price=None,
            currency=journeys[0].currency,
            results=journeys[:40],
            flexible_date_savings=[],
            generated_at=datetime.now(timezone.utc),
            data_mode="live",
            providers_used=["OctoTrip Flights"],
            notice=(
                "Real-time fares are supplied by OctoTrip. Metropolitan codes such as LON are expanded "
                "across their main airports. Prices and booking links are short-lived and should be rechecked."
            ),
        )

    async def _search_pair(
        self,
        client: httpx.AsyncClient,
        request: SearchRequest,
        origin: str,
        destination: str,
    ) -> list[Journey]:
        rpc = {
            "jsonrpc": "2.0",
            "id": f"{origin}-{destination}",
            "method": "tools/call",
            "params": {
                "name": "search",
                "arguments": {
                    "origin": origin,
                    "destination": destination,
                    "departure_date": request.departure_date.isoformat(),
                    "adults": request.passengers,
                    "children": 0,
                    "infants": 0,
                    "trip_class": "Y",
                    "currency": "GBP",
                    "locale": "en",
                },
            },
        }

        try:
            response = await client.post(
                OCTOTRIP_MCP,
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                    "User-Agent": "FareSphere/1.0",
                },
                json=rpc,
            )
            response.raise_for_status()
            payload = _extract_mcp_payload(response)
        except ProviderUnavailable:
            raise
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderUnavailable(f"OctoTrip {origin}→{destination} failed: {exc}") from exc

        if payload.get("error"):
            error = payload["error"]
            detail = error.get("message") or error.get("suggestion") or "No flight results."
            raise ProviderUnavailable(f"{origin}→{destination}: {detail}")

        origin_resolved = payload.get("origin_resolved") or {}
        destination_resolved = payload.get("destination_resolved") or {}
        journeys: list[Journey] = []

        for result in payload.get("results") or []:
            outbound = result.get("outbound") or {}
            raw_legs = outbound.get("legs") or []
            legs: list[Leg] = []

            for raw in raw_legs:
                origin_code = str(raw.get("departure") or origin)
                destination_code = str(raw.get("arrival") or destination)
                carrier = raw.get("carrier") or result.get("airline") or "Airline"
                legs.append(
                    Leg(
                        mode="flight",
                        carrier=carrier,
                        number=raw.get("flight_number"),
                        origin=_place(
                            origin_code,
                            origin_resolved if origin_code == origin_resolved.get("iata") else None,
                        ),
                        destination=_place(
                            destination_code,
                            destination_resolved if destination_code == destination_resolved.get("iata") else None,
                        ),
                        depart_at=_parse_datetime(raw.get("departure_date"), raw.get("departure_time")),
                        arrive_at=_parse_datetime(raw.get("arrival_date"), raw.get("arrival_time")),
                        ticket_price=0.0,
                        currency=result.get("currency") or "GBP",
                        price_verified=True,
                        source="OctoTrip real-time flight search",
                    )
                )

            if not legs and outbound.get("departure") and outbound.get("arrival"):
                legs.append(
                    Leg(
                        mode="flight",
                        carrier=result.get("airline") or "Airline",
                        number=(result.get("flight_numbers") or [None])[0],
                        origin=_place(str(outbound["departure"]), origin_resolved),
                        destination=_place(str(outbound["arrival"]), destination_resolved),
                        depart_at=_parse_datetime(outbound.get("departure_date"), outbound.get("departure_time")),
                        arrive_at=_parse_datetime(outbound.get("arrival_date"), outbound.get("arrival_time")),
                        ticket_price=0.0,
                        currency=result.get("currency") or "GBP",
                        price_verified=True,
                        source="OctoTrip real-time flight search",
                    )
                )

            if not legs:
                continue

            price = float(result.get("price") or 0)
            if price <= 0:
                continue
            legs[0].ticket_price = price

            stops = int(result.get("stops") or 0)
            badges = ["Live price", "Direct" if stops == 0 else f"{stops} stop" + ("s" if stops != 1 else "")]
            if result.get("baggage"):
                badges.append(str(result["baggage"])[:48])

            journeys.append(
                Journey(
                    id=str(uuid4()),
                    label=result.get("airline") or "Live flight",
                    legs=legs,
                    total_price=price,
                    currency=result.get("currency") or "GBP",
                    total_duration_minutes=int(
                        result.get("total_duration_minutes")
                        or outbound.get("duration_minutes")
                        or max(1, int((legs[-1].arrive_at - legs[0].depart_at).total_seconds() // 60))
                    ),
                    total_emissions_kg=None,
                    risk_score=min(100, 5 + stops * 8),
                    savings_vs_baseline=None,
                    badges=badges,
                    score=0.0,
                    price_verified=True,
                    source="OctoTrip real-time flight search",
                    source_offer_id=str(result.get("ignav_id") or result.get("id") or "") or None,
                    booking_url=result.get("booking_url"),
                )
            )

        return journeys
