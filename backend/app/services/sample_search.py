from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from math import radians, sin, cos, sqrt, atan2
from uuid import uuid4

from app.models import Journey, Leg, Place, SearchRequest, SearchResponse


PLACES: dict[str, Place] = {
    "LON": Place(code="LON", name="London", country="United Kingdom", lat=51.5074, lon=-0.1278),
    "LGW": Place(code="LGW", name="London Gatwick", country="United Kingdom", lat=51.1537, lon=-0.1821, kind="airport"),
    "STN": Place(code="STN", name="London Stansted", country="United Kingdom", lat=51.8850, lon=0.2350, kind="airport"),
    "LTN": Place(code="LTN", name="London Luton", country="United Kingdom", lat=51.8747, lon=-0.3683, kind="airport"),
    "MAN": Place(code="MAN", name="Manchester", country="United Kingdom", lat=53.4808, lon=-2.2426),
    "BCN": Place(code="BCN", name="Barcelona", country="Spain", lat=41.3874, lon=2.1686),
    "GRO": Place(code="GRO", name="Girona", country="Spain", lat=41.9794, lon=2.8214, kind="airport"),
    "PAR": Place(code="PAR", name="Paris", country="France", lat=48.8566, lon=2.3522),
    "AMS": Place(code="AMS", name="Amsterdam", country="Netherlands", lat=52.3676, lon=4.9041),
    "ROM": Place(code="ROM", name="Rome", country="Italy", lat=41.9028, lon=12.4964),
    "BGY": Place(code="BGY", name="Milan Bergamo", country="Italy", lat=45.6689, lon=9.7003, kind="airport"),
    "BRU": Place(code="BRU", name="Brussels", country="Belgium", lat=50.8503, lon=4.3517),
}


def _dt(day: date, hhmm: str, day_offset: int = 0) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(day + timedelta(days=day_offset), time(h, m), tzinfo=timezone.utc)


def _leg(mode, carrier, number, a, b, depart, arrive, fare, bag=0, transfer=0, co2=0, self_transfer=False):
    return Leg(
        mode=mode,
        carrier=carrier,
        number=number,
        origin=PLACES[a],
        destination=PLACES[b],
        depart_at=depart,
        arrive_at=arrive,
        ticket_price=fare,
        baggage_price=bag,
        transfer_price=transfer,
        emissions_kg=co2,
        self_transfer=self_transfer,
        price_verified=False,
        source="Sample data",
    )


def _minutes(legs: list[Leg]) -> int:
    return int((legs[-1].arrive_at - legs[0].depart_at).total_seconds() // 60)


def _risk(legs: list[Leg]) -> int:
    score = 8
    for leg in legs:
        if leg.self_transfer:
            score += 28
    score += max(0, len(legs) - 1) * 7
    return min(100, score)


def _cost(legs: list[Leg], bags: int, passengers: int) -> float:
    tickets = sum(x.ticket_price for x in legs) * passengers
    baggage = sum(x.baggage_price for x in legs) * bags
    transfers = sum(x.transfer_price for x in legs) * passengers
    return round(tickets + baggage + transfers, 2)


def _emissions(legs: list[Leg], passengers: int) -> float:
    return round(sum(x.emissions_kg for x in legs) * passengers, 1)


def _value_score(price: float, minutes: int, risk: int, baseline: float) -> float:
    price_component = price / max(baseline, 1)
    duration_component = minutes / (60 * 8)
    risk_component = risk / 100
    return round(price_component * 0.60 + duration_component * 0.25 + risk_component * 0.15, 4)


def _make(label: str, legs: list[Leg], req: SearchRequest, baseline: float, badges: list[str]) -> Journey:
    price = _cost(legs, req.checked_bags, req.passengers)
    duration = _minutes(legs)
    risk = _risk(legs)
    return Journey(
        id=str(uuid4()),
        label=label,
        legs=legs,
        total_price=price,
        total_duration_minutes=duration,
        total_emissions_kg=_emissions(legs, req.passengers),
        risk_score=risk,
        savings_vs_baseline=round(max(0, baseline - price), 2),
        badges=badges,
        score=_value_score(price, duration, risk, baseline),
        price_verified=False,
        source="Sample data",
    )


def _london_barcelona(req: SearchRequest) -> list[list]:
    d = req.departure_date
    return [
        ["Direct & simple", [
            _leg("train", "Thameslink", None, "LON", "LGW", _dt(d, "05:40"), _dt(d, "06:25"), 17, co2=1.5),
            _leg("flight", "Example Air", "EA412", "LGW", "BCN", _dt(d, "08:00"), _dt(d, "10:10"), 88, bag=32, co2=122),
        ], ["Fast", "Protected connection"]],
        ["Budget airport hack", [
            _leg("coach", "Airport Coach", None, "LON", "STN", _dt(d, "04:50"), _dt(d, "06:10"), 12, co2=4),
            _leg("flight", "LowFare", "LF221", "STN", "GRO", _dt(d, "07:25"), _dt(d, "10:30"), 34, bag=25, co2=119),
            _leg("coach", "Regional Bus", None, "GRO", "BCN", _dt(d, "11:05"), _dt(d, "12:20"), 16, co2=4),
        ], ["Cheapest", "Nearby airport"]],
        ["Low-carbon rail", [
            _leg("train", "Euro Rail", "ER901", "LON", "PAR", _dt(d, "06:30"), _dt(d, "08:50"), 56, co2=8),
            _leg("train", "TGV", "TGV9713", "PAR", "BCN", _dt(d, "10:15"), _dt(d, "16:45"), 72, co2=18),
        ], ["Low carbon", "City-centre arrival"]],
        ["Self-transfer saver", [
            _leg("flight", "LowFare", "LF104", "LTN", "BGY", _dt(d, "06:15"), _dt(d, "09:15"), 27, bag=24, transfer=10, co2=91),
            _leg("flight", "ValueJet", "VJ660", "BGY", "BCN", _dt(d, "12:20"), _dt(d, "13:55"), 30, bag=24, co2=64, self_transfer=True),
        ], ["Self-transfer", "Big saving"]],
    ]


def _generic(req: SearchRequest, origin: Place, destination: Place) -> list[list]:
    d = req.departure_date
    distance = max(250, haversine(origin.lat, origin.lon, destination.lat, destination.lon))
    base_fare = max(45, round(distance * 0.075, 0))
    duration_h = max(1.2, distance / 720)
    arrive = _dt(d, "08:00") + timedelta(hours=duration_h)
    direct = _leg("flight", "Example Air", "EA100", origin.code, destination.code, _dt(d, "08:00"), arrive, base_fare, bag=28, co2=distance * 0.115)
    saver = _leg("flight", "LowFare", "LF200", origin.code, destination.code, _dt(d, "14:10"), _dt(d, "14:10") + timedelta(hours=duration_h + 0.4), base_fare * 0.72, bag=24, co2=distance * 0.112)
    return [
        ["Direct", [direct], ["Fast", "Simple"]],
        ["Later departure deal", [saver], ["Cheapest", "Flexible time"]],
    ]


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * atan2(sqrt(a), sqrt(1 - a))


def search(req: SearchRequest) -> SearchResponse:
    origin = PLACES.get(req.origin.upper())
    destination = PLACES.get(req.destination.upper())
    if not origin or not destination:
        raise ValueError("Unknown origin or destination code.")

    candidates = _london_barcelona(req) if origin.code == "LON" and destination.code == "BCN" else _generic(req, origin, destination)

    baseline_legs = candidates[0][1]
    baseline = _cost(baseline_legs, req.checked_bags, req.passengers)
    journeys = [_make(label, legs, req, baseline, badges) for label, legs, badges in candidates]

    if req.sort == "cheapest":
        journeys.sort(key=lambda x: (x.total_price, x.total_duration_minutes))
    elif req.sort == "fastest":
        journeys.sort(key=lambda x: (x.total_duration_minutes, x.total_price))
    else:
        journeys.sort(key=lambda x: x.score)

    flexible = []
    for offset, factor in [(-2, 0.82), (-1, 0.94), (0, 1.0), (1, 0.88), (2, 0.79)]:
        if abs(offset) <= req.flexible_days:
            p = round(baseline * factor, 2)
            flexible.append({
                "date": (req.departure_date + timedelta(days=offset)).isoformat(),
                "from_price": p,
                "saving": round(max(0, baseline - p), 2),
            })

    return SearchResponse(
        origin=origin,
        destination=destination,
        baseline_price=baseline,
        results=journeys,
        flexible_date_savings=flexible,
        generated_at=datetime.now(timezone.utc),
        data_mode="sample",
        providers_used=["Sample data"],
        notice="Sample data for local development only. Prices are not live and must not be presented as bookable fares.",
    )
