from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import httpx

from app.core.config import settings
from app.models import Journey, Leg, Place, SearchRequest, SearchResponse
from app.providers.base import ProviderNotConfigured, ProviderUnavailable, UnsupportedLiveRequest


DUFFEL_API = "https://api.duffel.com"


def _place(payload: dict, fallback_code: str) -> Place:
    iata = payload.get("iata_code") or fallback_code
    name = payload.get("name") or payload.get("city_name") or iata
    return Place(
        code=iata,
        name=name,
        country=payload.get("iata_country_code") or payload.get("country_name") or "Unknown",
        lat=payload.get("latitude"),
        lon=payload.get("longitude"),
        kind="airport",
    )


def _parse_time(value: str) -> datetime:
    # Duffel timestamps are ISO 8601; normalise Z for Python's parser.
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _duration_minutes(legs: list[Leg]) -> int:
    return int((legs[-1].arrive_at - legs[0].depart_at).total_seconds() // 60)


def _risk(legs: list[Leg]) -> int:
    # Airline-protected segments remain one offer; risk here reflects connection complexity only.
    return min(100, 5 + max(0, len(legs) - 1) * 8)


class DuffelProvider:
    name = "Duffel"

    def __init__(self, client: httpx.AsyncClient | None = None, token: str | None = None):
        self._client = client
        self.token = settings.duffel_access_token if token is None else token

    async def search(self, request: SearchRequest) -> SearchResponse:
        if not self.token:
            raise ProviderNotConfigured("Duffel provider is not configured.")
        if request.checked_bags:
            raise UnsupportedLiveRequest(
                "Live checked-bag pricing is not enabled yet. Set checked bags to 0 so FareSphere does not guess ancillary prices."
            )
        if request.flexible_days:
            raise UnsupportedLiveRequest(
                "Live flexible-date pricing is not enabled yet. Set flexible_days to 0 so FareSphere does not invent adjacent-date prices."
            )

        payload = {
            "data": {
                "cabin_class": "economy",
                "slices": [
                    {
                        "origin": request.origin.upper(),
                        "destination": request.destination.upper(),
                        "departure_date": request.departure_date.isoformat(),
                    }
                ],
                "passengers": [{"type": "adult"} for _ in range(request.passengers)],
                "max_connections": 1,
            }
        }
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Duffel-Version": "v2",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        owns = self._client is None
        client = self._client or httpx.AsyncClient(timeout=35.0)
        try:
            response = await client.post(
                f"{DUFFEL_API}/air/offer_requests",
                params={"return_offers": "true", "supplier_timeout": 15000},
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            body = response.json().get("data") or {}
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"Duffel flight search failed: {exc}") from exc
        finally:
            if owns:
                await client.aclose()

        offers = body.get("offers") or []
        journeys: list[Journey] = []
        for offer in offers[:40]:
            slices = offer.get("slices") or []
            segments = [segment for slice_ in slices for segment in (slice_.get("segments") or [])]
            if not segments:
                continue

            legs: list[Leg] = []
            for segment in segments:
                origin_payload = segment.get("origin") or {}
                destination_payload = segment.get("destination") or {}
                operating = segment.get("operating_carrier") or {}
                marketing = segment.get("marketing_carrier") or operating
                carrier = operating.get("name") or marketing.get("name") or "Airline"
                flight_number = segment.get("marketing_carrier_flight_number")
                code = marketing.get("iata_code")
                number = f"{code}{flight_number}" if code and flight_number else str(flight_number or "") or None
                legs.append(
                    Leg(
                        mode="flight",
                        carrier=carrier,
                        number=number,
                        origin=_place(origin_payload, request.origin.upper()),
                        destination=_place(destination_payload, request.destination.upper()),
                        depart_at=_parse_time(segment["departing_at"]),
                        arrive_at=_parse_time(segment["arriving_at"]),
                        ticket_price=0.0,
                        currency=offer.get("total_currency") or "GBP",
                        emissions_kg=(float(segment["carbon_emissions_kg"]) if segment.get("carbon_emissions_kg") else None),
                        price_verified=True,
                        source="Duffel live offer",
                    )
                )

            currency = offer.get("total_currency") or "GBP"
            total_price = float(offer.get("total_amount") or 0)
            legs[0].ticket_price = total_price
            emissions = offer.get("total_emissions_kg")
            total_emissions = float(emissions) if emissions is not None else None
            duration = _duration_minutes(legs)
            journeys.append(
                Journey(
                    id=str(uuid4()),
                    label=" · ".join(dict.fromkeys(leg.carrier for leg in legs)),
                    legs=legs,
                    total_price=total_price,
                    currency=currency,
                    total_duration_minutes=duration,
                    total_emissions_kg=total_emissions,
                    risk_score=_risk(legs),
                    savings_vs_baseline=None,
                    badges=["Live price", "Direct" if len(legs) == 1 else f"{len(legs)-1} stop"],
                    score=0.0,
                    price_verified=True,
                    source="Duffel live offer",
                    source_offer_id=offer.get("id"),
                )
            )

        if not journeys:
            raise ProviderUnavailable("Duffel returned no live offers for this search.")

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

        baseline = None
        first_origin = journeys[0].legs[0].origin
        last_destination = journeys[0].legs[-1].destination
        return SearchResponse(
            origin=first_origin,
            destination=last_destination,
            baseline_price=baseline,
            currency=journeys[0].currency,
            results=journeys,
            flexible_date_savings=[],
            generated_at=datetime.now(timezone.utc),
            data_mode="live",
            providers_used=["Duffel"],
            notice="Prices are live search results and may change or expire; re-fetch the selected offer before booking.",
        )
