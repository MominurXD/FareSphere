from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

import httpx

from app.models import Journey, Leg, Place, SearchRequest, SearchResponse
from app.providers.base import ProviderUnavailable, UnsupportedLiveRequest


OCTOTRIP_MCP = "https://mcp.octotrip.app/flights/mcp"


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

    async def search(self, request: SearchRequest) -> SearchResponse:
        if request.checked_bags:
            raise UnsupportedLiveRequest(
                "FareSphere does not add guessed checked-bag charges. Search with checked_bags=0."
            )
        if request.flexible_days:
            raise UnsupportedLiveRequest(
                "Flexible-date pricing is not enabled for this live provider. Set flexible_days=0."
            )

        rpc = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "search",
                "arguments": {
                    "origin": request.origin.upper(),
                    "destination": request.destination.upper(),
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

        owns = self._client is None
        client = self._client or httpx.AsyncClient(timeout=45.0)
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
            raise ProviderUnavailable(f"OctoTrip live flight search failed: {exc}") from exc
        finally:
            if owns:
                await client.aclose()

        if payload.get("error"):
            error = payload["error"]
            detail = error.get("message") or error.get("suggestion") or "No flight results."
            raise ProviderUnavailable(detail)

        origin_resolved = payload.get("origin_resolved") or {}
        destination_resolved = payload.get("destination_resolved") or {}
        journeys: list[Journey] = []

        for result in payload.get("results") or []:
            outbound = result.get("outbound") or {}
            raw_legs = outbound.get("legs") or []
            legs: list[Leg] = []

            for raw in raw_legs:
                origin_code = str(raw.get("departure") or request.origin.upper())
                destination_code = str(raw.get("arrival") or request.destination.upper())
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

            # Some results include only an outbound summary; keep them usable.
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
                    total_duration_minutes=int(result.get("total_duration_minutes") or outbound.get("duration_minutes") or 1),
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

        if not journeys:
            raise ProviderUnavailable("OctoTrip returned no live fares for this route/date.")

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
            results=journeys,
            flexible_date_savings=[],
            generated_at=datetime.utcnow(),
            data_mode="live",
            providers_used=["OctoTrip Flights"],
            notice=(
                "Real-time fares are supplied by OctoTrip and are typically valid for about 15 minutes. "
                "Booking links may contain affiliate attribution; FareSphere itself does not sell tickets."
            ),
        )
