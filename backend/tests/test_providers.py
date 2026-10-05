from datetime import date, datetime
from zoneinfo import ZoneInfo

import asyncio
import json

import httpx

from app.models import SearchRequest
from app.providers.duffel import DuffelProvider
from app.providers.national_rail import NationalRailProvider
from app.providers.octotrip import OctoTripProvider
from app.providers.tfl import TfLProvider
from app.providers.tfl_journey import TfLJourneyProvider, is_london_ground_journey


def test_duffel_parses_live_offer_without_guessing_price():
    async def _run():
        async def handler(request: httpx.Request):
            return httpx.Response(
                200,
                json={"data": {"offers": [{
                    "id": "off_123", "total_amount": "84.70", "total_currency": "GBP",
                    "slices": [{"segments": [{
                        "departing_at": "2026-11-14T08:00:00+00:00",
                        "arriving_at": "2026-11-14T10:10:00+00:00",
                        "origin": {"iata_code": "LGW", "name": "Gatwick Airport", "iata_country_code": "GB"},
                        "destination": {"iata_code": "BCN", "name": "Barcelona Airport", "iata_country_code": "ES"},
                        "operating_carrier": {"name": "Example Carrier", "iata_code": "EX"},
                        "marketing_carrier": {"name": "Example Carrier", "iata_code": "EX"},
                        "marketing_carrier_flight_number": "412",
                    }]}],
                }]}}
            )
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            result = await DuffelProvider(client=client, token="test-token").search(SearchRequest(
                origin="LGW", destination="BCN", departure_date=date(2026, 11, 14),
                passengers=1, checked_bags=0, flexible_days=0, sort="cheapest",
            ))
        finally:
            await client.aclose()
        assert result.results[0].total_price == 84.70
        assert result.results[0].legs[0].number == "EX412"
    asyncio.run(_run())


def _octotrip_sse(origin: str, destination: str, price: float) -> str:
    payload = {
        "results": [{
            "airline": "Example Air",
            "flight_numbers": ["EA123"],
            "is_direct": True,
            "stops": 0,
            "total_duration_minutes": 130,
            "outbound": {
                "departure": origin, "arrival": destination,
                "departure_time": "08:00", "arrival_time": "10:10",
                "departure_date": "2026-11-14", "arrival_date": "2026-11-14",
                "duration_minutes": 130,
                "legs": [{
                    "flight_number": "EA123", "carrier": "Example Air",
                    "departure": origin, "arrival": destination,
                    "departure_time": "08:00", "arrival_time": "10:10",
                    "departure_date": "2026-11-14", "arrival_date": "2026-11-14",
                    "duration_minutes": 130,
                }],
            },
            "price": price,
            "currency": "GBP",
            "baggage": "Cabin bag included",
            "booking_url": "https://provider.example/book",
        }],
        "origin_resolved": {"iata": origin, "name": origin, "country_code": "GB"},
        "destination_resolved": {"iata": destination, "name": destination, "country_code": "ES"},
    }
    rpc = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": json.dumps(payload)}]}}
    return f"event: message\ndata: {json.dumps(rpc)}\n\n"


def test_octotrip_parses_sse_live_fares_inside_app():
    async def _run():
        async def handler(request: httpx.Request):
            assert request.url.path == "/flights/mcp"
            return httpx.Response(
                200,
                text=_octotrip_sse("LGW", "BCN", 44.75),
                headers={"content-type": "text/event-stream"},
            )
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            result = await OctoTripProvider(client=client).search(SearchRequest(
                origin="LGW", destination="BCN", departure_date=date(2026, 11, 14),
                passengers=1, checked_bags=0, flexible_days=0, sort="cheapest",
            ))
        finally:
            await client.aclose()
        assert result.results[0].total_price == 44.75
        assert result.results[0].legs[0].number == "EA123"
    asyncio.run(_run())


def test_octotrip_expands_lon_to_real_airports():
    async def _run():
        seen: set[str] = set()

        async def handler(request: httpx.Request):
            body = json.loads(request.content)
            args = body["params"]["arguments"]
            origin = args["origin"]
            seen.add(origin)
            if origin == "LGW":
                return httpx.Response(
                    200,
                    text=_octotrip_sse("LGW", "BCN", 39.99),
                    headers={"content-type": "text/event-stream"},
                )
            empty = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": json.dumps({"results": []})}]}}
            return httpx.Response(
                200,
                text=f"data: {json.dumps(empty)}\n\n",
                headers={"content-type": "text/event-stream"},
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            result = await OctoTripProvider(client=client).search(SearchRequest(
                origin="LON", destination="BCN", departure_date=date(2026, 11, 14),
                passengers=1, checked_bags=0, flexible_days=0, sort="cheapest",
            ))
        finally:
            await client.aclose()

        assert {"LHR", "LGW", "STN", "LTN", "LCY"}.issubset(seen)
        assert result.results[0].legs[0].origin.code == "LGW"
        assert result.results[0].total_price == 39.99
    asyncio.run(_run())


def test_lon_to_heathrow_is_ground_transport():
    assert is_london_ground_journey("LON", "LHR")
    assert is_london_ground_journey("LHR", "LON")
    assert not is_london_ground_journey("LON", "BCN")


def test_tfl_journey_parses_real_fare_and_multiplies_travellers():
    async def _run():
        async def handler(request: httpx.Request):
            assert request.url.path.startswith("/Journey/JourneyResults/")
            assert request.url.params["date"] == "20261026"
            assert request.url.params["time"] == "0900"
            modes = request.url.params["mode"].split(",")
            assert "public-bus" not in modes
            assert "train" not in modes
            assert {"bus", "tube", "elizabeth-line", "national-rail", "walking"}.issubset(set(modes))
            return httpx.Response(200, json={
                "journeys": [{
                    "startDateTime": "2026-10-26T09:00:00",
                    "arrivalDateTime": "2026-10-26T09:47:00",
                    "duration": 47,
                    "fare": {
                        "totalCost": 580,
                        "fares": [{"cost": 580, "lowZone": 1, "highZone": 6}],
                    },
                    "legs": [
                        {
                            "departureTime": "2026-10-26T09:00:00",
                            "arrivalTime": "2026-10-26T09:05:00",
                            "departurePoint": {"commonName": "Westminster", "lat": 51.5007, "lon": -0.1246},
                            "arrivalPoint": {"commonName": "Tottenham Court Road", "lat": 51.5165, "lon": -0.1309},
                            "mode": {"id": "walking", "name": "walking"},
                            "routeOptions": [],
                        },
                        {
                            "departureTime": "2026-10-26T09:05:00",
                            "arrivalTime": "2026-10-26T09:47:00",
                            "departurePoint": {"commonName": "Tottenham Court Road", "lat": 51.5165, "lon": -0.1309},
                            "arrivalPoint": {"commonName": "Heathrow Terminal 2 & 3", "lat": 51.4713, "lon": -0.4524},
                            "mode": {"id": "train", "name": "train"},
                            "routeOptions": [{"name": "Elizabeth line"}],
                        },
                    ],
                }]
            })

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            result = await TfLJourneyProvider(client=client, app_key="").search(SearchRequest(
                origin="LON", destination="LHR", departure_date=date(2026, 10, 26),
                departure_time="09:00", passengers=2, checked_bags=0, flexible_days=0, sort="best",
            ))
        finally:
            await client.aclose()

        assert result.providers_used == ["Transport for London Journey Planner"]
        assert result.origin.code == "LON"
        assert result.destination.code == "LHR"
        assert result.results[0].total_price == 11.60
        assert "£5.80 pp" in result.results[0].badges
        assert result.results[0].label == "Elizabeth line"
        assert result.results[0].price_verified is True
    asyncio.run(_run())


def test_tfl_network_parses_real_line_shape_without_key():
    async def _run():
        async def handler(request: httpx.Request):
            assert "app_key" not in request.url.params
            if request.url.path == "/Line/Mode/tube,overground,elizabeth-line,dlr":
                return httpx.Response(200, json=[{"id": "central"}])
            return httpx.Response(200, json={
                "lineName": "Central",
                "stopPointSequences": [{"stopPoint": [
                    {"id": "a", "name": "A", "lat": 51.5, "lon": -0.2},
                    {"id": "b", "name": "B", "lat": 51.51, "lon": -0.1},
                ]}],
            })
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            result = await TfLProvider(client=client, app_key="").network()
        finally:
            await client.aclose()
        assert result.paths[0].name == "Central"
        assert len(result.paths[0].points) == 2
    asyncio.run(_run())


def test_national_rail_uses_trainiac_v1_without_owner_api_key():
    async def _run():
        async def handler(request: httpx.Request):
            assert request.url.path == "/v1/departures/KGX"
            assert request.url.params["limit"] == "10"
            return httpx.Response(200, json={
                "type": "ok",
                "request": {
                    "station": {
                        "query": "KGX",
                        "resolution": {"type": "station", "crs": "KGX", "name": "London Kings Cross"},
                    },
                    "calling_at": None,
                    "from_time": None,
                    "to_time": None,
                    "limit": 10,
                },
                "data": [{
                    "train": {
                        "id": "123",
                        "uid": "C123",
                        "headcode": "1A23",
                        "operator": {"code": "GR", "name": "LNER"},
                    },
                    "service_class": "passenger",
                    "origin": {"type": "station", "crs": "KGX", "name": "London Kings Cross"},
                    "destination": {"type": "station", "crs": "EDB", "name": "Edinburgh"},
                    "departs": {
                        "scheduled": "2026-10-05T22:10:00+01:00",
                        "estimate": {"type": "forecast", "at": "2026-10-05T22:14:00+01:00", "source": "darwin"},
                        "delay_minutes": 4,
                    },
                    "platform": {"type": "known", "number": "5", "source": "forecast"},
                    "calling_points": [],
                    "destination_arrival": "2026-10-06T02:30:00+01:00",
                    "coaches": None,
                    "formation_changes": [],
                    "formed_from": None,
                    "delay_reason": None,
                    "advertised": True,
                }],
                "generated_at": "2026-10-05T22:00:00+01:00",
            })

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            result = await NationalRailProvider(
                client=client,
                api_key="",
                trainiac_base_url="https://api.traini.ac",
            ).departures("kgx")
        finally:
            await client.aclose()

        assert result.station == "KGX"
        assert result.provider.startswith("traini.ac")
        assert result.departures[0].destination == "Edinburgh"
        assert result.departures[0].scheduled == "22:10"
        assert result.departures[0].expected == "22:14"
        assert result.departures[0].platform == "5"
    asyncio.run(_run())


def test_national_rail_station_search_and_live_journey_have_no_fake_fare():
    async def _run():
        today = datetime.now(ZoneInfo("Europe/London")).date()

        async def handler(request: httpx.Request):
            if request.url.path == "/v1/stations":
                query = request.url.params["q"]
                crs = "EUS" if query.upper() == "EUS" else "MAN"
                name = "London Euston" if crs == "EUS" else "Manchester Piccadilly"
                return httpx.Response(200, json={
                    "type": "ok",
                    "request": {"q": query},
                    "data": {
                        "resolves_to": {"type": "station", "crs": crs, "name": name},
                        "matches": [{"type": "station", "crs": crs, "name": name, "tiploc": crs, "stanox": None, "calls_today": 100}],
                        "near_misses": False,
                    },
                    "generated_at": "2026-10-05T22:00:00+01:00",
                })

            assert request.url.path == "/v1/journey/EUS/MAN"
            assert request.url.params["from_time"] == "09:00"
            return httpx.Response(200, json={
                "type": "ok",
                "request": {},
                "data": [{
                    "type": "direct",
                    "departs": {
                        "scheduled": f"{today.isoformat()}T09:13:00+01:00",
                        "estimate": {"type": "forecast", "at": f"{today.isoformat()}T09:15:00+01:00", "source": "darwin"},
                        "delay_minutes": 2,
                    },
                    "arrives": {
                        "scheduled": f"{today.isoformat()}T11:20:00+01:00",
                        "estimate": {"type": "forecast", "at": f"{today.isoformat()}T11:22:00+01:00", "source": "darwin"},
                        "delay_minutes": 2,
                    },
                    "duration_minutes": 127,
                    "leg": {
                        "train": {"id": "T1", "uid": "U1", "headcode": "1H01", "operator": {"code": "VT", "name": "Avanti West Coast"}},
                        "service_class": "passenger",
                        "from": {"type": "station", "crs": "EUS", "name": "London Euston"},
                        "departs": {
                            "scheduled": f"{today.isoformat()}T09:13:00+01:00",
                            "estimate": {"type": "forecast", "at": f"{today.isoformat()}T09:15:00+01:00", "source": "darwin"},
                            "delay_minutes": 2,
                        },
                        "departure_platform": {"type": "known", "number": "6", "source": "forecast"},
                        "to": {"type": "station", "crs": "MAN", "name": "Manchester Piccadilly"},
                        "arrives": {
                            "scheduled": f"{today.isoformat()}T11:20:00+01:00",
                            "estimate": {"type": "forecast", "at": f"{today.isoformat()}T11:22:00+01:00", "source": "darwin"},
                            "delay_minutes": 2,
                        },
                        "arrival_platform": {"type": "known", "number": "7", "source": "forecast"},
                        "coaches": 11,
                    },
                }],
                "generated_at": f"{today.isoformat()}T08:55:00+01:00",
            })

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        provider = NationalRailProvider(client=client, api_key="", trainiac_base_url="https://api.traini.ac")
        try:
            assert await provider.resolves_as_rail("EUS") is True
            assert await provider.resolves_as_rail("MAN") is True
            result = await provider.journeys(SearchRequest(
                origin="EUS",
                destination="MAN",
                departure_date=today,
                departure_time="09:00",
                passengers=1,
                checked_bags=0,
                flexible_days=0,
                sort="best",
            ))
        finally:
            await client.aclose()

        assert result.providers_used == ["GB Rail Live (traini.ac)"]
        assert result.results[0].total_price is None
        assert result.results[0].price_verified is False
        assert result.results[0].legs[0].platform == "6"
        assert result.results[0].legs[0].number == "1H01"
        assert "Fare not supplied" in result.results[0].badges
    asyncio.run(_run())
