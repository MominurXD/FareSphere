from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import httpx

from app.core.config import settings
from app.models import Journey, Leg, Place, SearchRequest, SearchResponse
from app.providers.base import ProviderNotConfigured, ProviderUnavailable, UnsupportedLiveRequest


SKYSCANNER_API = "https://partners.api.skyscanner.net/apiservices/v3/flights/live"


def _dt(value: dict | None) -> datetime:
    value = value or {}
    return datetime(
        int(value.get("year") or 1970),
        int(value.get("month") or 1),
        int(value.get("day") or 1),
        int(value.get("hour") or 0),
        int(value.get("minute") or 0),
        int(value.get("second") or 0),
    )


def _money(price: dict | None) -> float:
    price = price or {}
    amount = float(price.get("amount") or 0)
    unit = str(price.get("unit") or "")
    if unit.endswith("MICRO"):
        return amount / 1_000_000
    if unit.endswith("MILLI"):
        return amount / 1_000
    if unit.endswith("CENTI"):
        return amount / 100
    return amount


def _place(payload: dict | None, fallback: str) -> Place:
    payload = payload or {}
    coords = payload.get("coordinates") or {}
    return Place(
        code=payload.get("iata") or fallback,
        name=payload.get("name") or payload.get("iata") or fallback,
        country="Unknown",
        lat=coords.get("latitude"),
        lon=coords.get("longitude"),
        kind="airport",
    )


class SkyscannerProvider:
    name = "Skyscanner"

    def __init__(self, client: httpx.AsyncClient | None = None, api_key: str | None = None):
        self._client = client
        self.api_key = settings.skyscanner_api_key if api_key is None else api_key

    async def search(self, request: SearchRequest) -> SearchResponse:
        if not self.api_key:
            raise ProviderNotConfigured("Skyscanner provider is not configured.")
        if request.checked_bags:
            raise UnsupportedLiveRequest(
                "Checked-bag pricing requires Skyscanner baggage access; set checked bags to 0."
            )
        if request.flexible_days:
            raise UnsupportedLiveRequest(
                "Live flexible-date search is not enabled in this endpoint; set flexible_days to 0."
            )

        payload = {
            "query": {
                "market": "UK",
                "locale": "en-GB",
                "currency": "GBP",
                "queryLegs": [{
                    "originPlaceId": {"iata": request.origin.upper()},
                    "destinationPlaceId": {"iata": request.destination.upper()},
                    "date": {
                        "year": request.departure_date.year,
                        "month": request.departure_date.month,
                        "day": request.departure_date.day,
                    },
                }],
                "adults": request.passengers,
                "cabinClass": "CABIN_CLASS_ECONOMY",
            }
        }
        headers = {"x-api-key": self.api_key, "Accept": "application/json", "Content-Type": "application/json"}

        owns = self._client is None
        client = self._client or httpx.AsyncClient(timeout=35.0)
        body: dict = {}
        try:
            response = await client.post(f"{SKYSCANNER_API}/search/create", headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()

            session = body.get("sessionToken")
            # Poll once to allow slower suppliers to add live inventory while keeping
            # user-facing latency bounded. If polling fails, the create payload remains usable.
            if session:
                await asyncio.sleep(0.25)
                try:
                    poll = await client.post(f"{SKYSCANNER_API}/search/poll/{session}", headers=headers)
                    poll.raise_for_status()
                    polled = poll.json()
                    if (polled.get("content") or {}).get("results"):
                        body = polled
                except httpx.HTTPError:
                    pass
        except httpx.HTTPStatusError as exc:
            detail = f"Skyscanner returned HTTP {exc.response.status_code}."
            if exc.response.status_code in {401, 403}:
                detail += " Check the approved Skyscanner partner API key and product access."
            raise ProviderUnavailable(detail) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"Skyscanner flight search failed: {exc}") from exc
        finally:
            if owns:
                await client.aclose()

        results = ((body.get("content") or {}).get("results") or {})
        itineraries = results.get("itineraries") or {}
        legs = results.get("legs") or {}
        segments = results.get("segments") or {}
        places = results.get("places") or {}
        carriers = results.get("carriers") or {}

        journeys: list[Journey] = []
        for itinerary_id, itinerary in list(itineraries.items())[:40]:
            pricing = itinerary.get("pricingOptions") or []
            if not pricing:
                continue
            cheapest_option = min(pricing, key=lambda p: _money(p.get("price")))
            total_price = _money(cheapest_option.get("price"))
            if total_price <= 0:
                continue

            parsed_legs: list[Leg] = []
            carrier_names: list[str] = []
            total_duration = 0
            stop_count = 0

            for leg_id in itinerary.get("legIds") or []:
                leg_payload = legs.get(leg_id) or {}
                total_duration += int(leg_payload.get("durationInMinutes") or 0)
                stop_count += int(leg_payload.get("stopCount") or 0)

                for segment_id in leg_payload.get("segmentIds") or []:
                    segment = segments.get(segment_id) or {}
                    origin_id = segment.get("originPlaceId")
                    destination_id = segment.get("destinationPlaceId")
                    carrier_id = segment.get("marketingCarrierId") or segment.get("operatingCarrierId")
                    carrier_payload = carriers.get(carrier_id) or {}
                    carrier_name = carrier_payload.get("name") or "Airline"
                    carrier_names.append(carrier_name)
                    display_code = carrier_payload.get("displayCode") or carrier_payload.get("iata")
                    flight_number = segment.get("marketingFlightNumber")
                    number = f"{display_code}{flight_number}" if display_code and flight_number else str(flight_number or "") or None

                    parsed_legs.append(
                        Leg(
                            mode="flight",
                            carrier=carrier_name,
                            number=number,
                            origin=_place(places.get(origin_id), request.origin.upper()),
                            destination=_place(places.get(destination_id), request.destination.upper()),
                            depart_at=_dt(segment.get("departureDateTime")),
                            arrive_at=_dt(segment.get("arrivalDateTime")),
                            ticket_price=0.0,
                            currency="GBP",
                            price_verified=True,
                            source="Skyscanner live price",
                        )
                    )

            if not parsed_legs:
                continue
            parsed_legs[0].ticket_price = total_price
            item = (cheapest_option.get("items") or [{}])[0] or {}
            booking_url = item.get("deepLink")

            journeys.append(
                Journey(
                    id=str(uuid4()),
                    label=" · ".join(dict.fromkeys(carrier_names)) or "Live flight",
                    legs=parsed_legs,
                    total_price=round(total_price, 2),
                    currency="GBP",
                    total_duration_minutes=total_duration or max(
                        1, int((parsed_legs[-1].arrive_at - parsed_legs[0].depart_at).total_seconds() // 60)
                    ),
                    total_emissions_kg=None,
                    risk_score=min(100, 5 + stop_count * 8),
                    savings_vs_baseline=None,
                    badges=["Live price", "Direct" if stop_count == 0 else f"{stop_count} stop" + ("s" if stop_count != 1 else "")],
                    score=0.0,
                    price_verified=True,
                    source="Skyscanner Flights Live Prices",
                    source_offer_id=cheapest_option.get("id") or itinerary_id,
                    booking_url=booking_url,
                )
            )

        if not journeys:
            raise ProviderUnavailable("Skyscanner returned no live itineraries for this search.")

        if request.sort == "fastest":
            journeys.sort(key=lambda item: (item.total_duration_minutes, item.total_price))
        elif request.sort == "best":
            cheapest = min(item.total_price for item in journeys) or 1.0
            fastest = min(item.total_duration_minutes for item in journeys) or 1
            for item in journeys:
                item.score = round((item.total_price / cheapest) * 0.65 + (item.total_duration_minutes / fastest) * 0.35, 4)
            journeys.sort(key=lambda item: item.score)
        else:
            journeys.sort(key=lambda item: (item.total_price, item.total_duration_minutes))

        return SearchResponse(
            origin=journeys[0].legs[0].origin,
            destination=journeys[0].legs[-1].destination,
            baseline_price=None,
            currency="GBP",
            results=journeys,
            flexible_date_savings=[],
            generated_at=datetime.now(timezone.utc),
            data_mode="live",
            providers_used=["Skyscanner"],
            notice="Live provider prices can change. Recheck the selected itinerary with the booking provider before purchase.",
        )
