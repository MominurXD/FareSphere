from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import httpx

from app.core.config import settings
from app.models import Journey, Leg, Place, SearchRequest, SearchResponse
from app.providers.base import ProviderUnavailable, UnsupportedLiveRequest


TFL_API = "https://api.tfl.gov.uk"

LONDON_PLACES: dict[str, Place] = {
    "LON": Place(
        code="LON",
        name="Central London (Westminster)",
        country="GB",
        lat=51.5007,
        lon=-0.1246,
        kind="city",
    ),
    "LHR": Place(
        code="LHR",
        name="London Heathrow Airport",
        country="GB",
        lat=51.4700,
        lon=-0.4543,
        kind="airport",
    ),
    "LCY": Place(
        code="LCY",
        name="London City Airport",
        country="GB",
        lat=51.5053,
        lon=0.0553,
        kind="airport",
    ),
    "LGW": Place(
        code="LGW",
        name="London Gatwick Airport",
        country="GB",
        lat=51.1537,
        lon=-0.1821,
        kind="airport",
    ),
    "LTN": Place(
        code="LTN",
        name="London Luton Airport",
        country="GB",
        lat=51.8747,
        lon=-0.3683,
        kind="airport",
    ),
    "STN": Place(
        code="STN",
        name="London Stansted Airport",
        country="GB",
        lat=51.8850,
        lon=0.2350,
        kind="airport",
    ),
}


def is_london_ground_journey(origin: str, destination: str) -> bool:
    origin = origin.upper()
    destination = destination.upper()
    return origin != destination and origin in LONDON_PLACES and destination in LONDON_PLACES


def _dt(value: str | None) -> datetime:
    if not value:
        raise ValueError("TfL journey leg is missing a time.")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _code(name: str | None, fallback: str = "TFL") -> str:
    if not name:
        return fallback
    letters = "".join(ch for ch in name.upper() if ch.isalnum())
    return letters[:3] or fallback


def _point_place(point: dict | None, fallback_code: str | None = None) -> Place:
    point = point or {}
    name = point.get("commonName") or point.get("name") or fallback_code or "TfL stop"
    return Place(
        code=fallback_code or _code(name),
        name=name,
        country="GB",
        lat=point.get("lat"),
        lon=point.get("lon"),
        kind="station",
    )


def _mode(raw: str) -> str:
    value = raw.lower()
    if value in {"walking", "walk"}:
        return "walk"
    if value in {"train", "national-rail"}:
        return "train"
    if value in {"tube", "overground", "dlr", "tram", "elizabeth-line"}:
        return "metro"
    if value in {"bus", "public-bus", "coach"}:
        return "coach"
    return "metro"


def _route_name(leg: dict) -> str:
    options = leg.get("routeOptions") or []
    for option in options:
        line = option.get("lineIdentifier") or {}
        name = option.get("name") or line.get("name") or line.get("id")
        if name:
            return str(name)
    mode = leg.get("mode") or {}
    return str(mode.get("name") or mode.get("id") or "TfL")


class TfLJourneyProvider:
    name = "Transport for London Journey Planner"

    def __init__(self, client: httpx.AsyncClient | None = None, app_key: str | None = None):
        self._client = client
        self.app_key = settings.tfl_app_key if app_key is None else app_key

    async def search(self, request: SearchRequest) -> SearchResponse:
        origin_code = request.origin.upper()
        destination_code = request.destination.upper()
        if not is_london_ground_journey(origin_code, destination_code):
            raise UnsupportedLiveRequest("This route is not a London-area ground journey.")

        origin = LONDON_PLACES[origin_code]
        destination = LONDON_PLACES[destination_code]
        from_value = f"{origin.lat},{origin.lon}"
        to_value = f"{destination.lat},{destination.lon}"

        params = {
            "date": request.departure_date.strftime("%Y%m%d"),
            "time": request.departure_time.replace(":", ""),
            "timeIs": "departing",
            "journeyPreference": "leasttime",
            "mode": "public-bus,overground,train,tube,dlr,walking",
            "nationalSearch": "true",
            "useRealTimeLiveArrivals": "true",
        }
        if self.app_key:
            params["app_key"] = self.app_key

        owns = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30.0)
        try:
            response = await client.get(
                f"{TFL_API}/Journey/JourneyResults/{from_value}/to/{to_value}",
                params=params,
                headers={"Accept": "application/json", "User-Agent": "FareSphere/1.0"},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            detail = f"TfL Journey Planner returned HTTP {exc.response.status_code}."
            try:
                body = exc.response.json()
                if isinstance(body, dict) and body.get("message"):
                    detail += f" {body['message']}"
            except ValueError:
                pass
            raise ProviderUnavailable(detail) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailable(f"TfL Journey Planner failed: {exc}") from exc
        finally:
            if owns:
                await client.aclose()

        journeys: list[Journey] = []
        for item in payload.get("journeys") or []:
            fare = item.get("fare") or {}
            fare_pence = fare.get("totalCost")
            if not fare_pence:
                fare_pence = sum(
                    int(row.get("cost") or 0)
                    for row in (fare.get("fares") or [])
                    if isinstance(row, dict)
                )
            if not fare_pence or int(fare_pence) <= 0:
                # FareSphere does not invent a price where TfL did not quote one.
                continue

            fare_per_person = round(int(fare_pence) / 100, 2)
            total_price = round(fare_per_person * request.passengers, 2)
            raw_legs = item.get("legs") or []
            legs: list[Leg] = []
            route_names: list[str] = []
            charge_assigned = False

            for index, raw_leg in enumerate(raw_legs):
                raw_mode = str((raw_leg.get("mode") or {}).get("id") or (raw_leg.get("mode") or {}).get("name") or "")
                mapped_mode = _mode(raw_mode)
                route_name = _route_name(raw_leg)
                if mapped_mode != "walk" and route_name and route_name not in route_names:
                    route_names.append(route_name)

                dep = _point_place(
                    raw_leg.get("departurePoint"),
                    origin_code if index == 0 else None,
                )
                arr = _point_place(
                    raw_leg.get("arrivalPoint"),
                    destination_code if index == len(raw_legs) - 1 else None,
                )
                leg_price = 0.0
                if mapped_mode != "walk" and not charge_assigned:
                    leg_price = total_price
                    charge_assigned = True

                legs.append(
                    Leg(
                        mode=mapped_mode,
                        carrier=route_name or "Transport for London",
                        number=None,
                        origin=dep,
                        destination=arr,
                        depart_at=_dt(raw_leg.get("departureTime") or raw_leg.get("scheduledDepartureTime")),
                        arrive_at=_dt(raw_leg.get("arrivalTime") or raw_leg.get("scheduledArrivalTime")),
                        ticket_price=leg_price,
                        currency="GBP",
                        price_verified=True,
                        source="Transport for London Journey Planner",
                    )
                )

            if not legs:
                continue

            changes = max(0, len([leg for leg in legs if leg.mode != "walk"]) - 1)
            label = " + ".join(route_names) if route_names else "TfL public transport"
            badges = [
                "TfL live journey",
                f"£{fare_per_person:.2f} pp",
                "Direct" if changes == 0 else f"{changes} change" + ("s" if changes != 1 else ""),
            ]
            journeys.append(
                Journey(
                    id=str(uuid4()),
                    label=label,
                    legs=legs,
                    total_price=total_price,
                    currency="GBP",
                    total_duration_minutes=int(item.get("duration") or 1),
                    total_emissions_kg=None,
                    risk_score=min(35, 5 + changes * 6),
                    savings_vs_baseline=None,
                    badges=badges,
                    score=0.0,
                    price_verified=True,
                    source="Transport for London Journey Planner",
                )
            )

        if not journeys:
            raise ProviderUnavailable(
                "TfL found no journey with a quoted fare for this London-area route and time."
            )

        if request.sort == "fastest":
            journeys.sort(key=lambda item: (item.total_duration_minutes, item.total_price))
        elif request.sort == "cheapest":
            journeys.sort(key=lambda item: (item.total_price, item.total_duration_minutes))
        else:
            cheapest = min(j.total_price for j in journeys) or 1
            fastest = min(j.total_duration_minutes for j in journeys) or 1
            for journey in journeys:
                journey.score = round(
                    (journey.total_price / cheapest) * 0.55
                    + (journey.total_duration_minutes / fastest) * 0.45,
                    4,
                )
            journeys.sort(key=lambda item: item.score)

        notice_parts = [
            f"{origin_code} is interpreted as {origin.name}." if origin_code == "LON" else "",
            f"{destination_code} is interpreted as {destination.name}." if destination_code == "LON" else "",
            (
                f"TfL quoted fares for a {request.departure_time} departure on "
                f"{request.departure_date.isoformat()}; the card total is for {request.passengers} traveller"
                + ("s." if request.passengers != 1 else ".")
            ),
            "Actual fare can vary with payment method, route, concessions and service changes.",
        ]

        return SearchResponse(
            origin=origin,
            destination=destination,
            baseline_price=None,
            currency="GBP",
            results=journeys,
            flexible_date_savings=[],
            generated_at=datetime.now(timezone.utc),
            data_mode="live",
            providers_used=["Transport for London Journey Planner"],
            notice=" ".join(part for part in notice_parts if part),
        )
