from datetime import date

import asyncio
import json

import httpx

from app.models import SearchRequest
from app.providers.duffel import DuffelProvider
from app.providers.national_rail import NationalRailProvider
from app.providers.octotrip import OctoTripProvider
from app.providers.tfl import TfLProvider


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


def test_national_rail_uses_trainiac_without_owner_api_key():
    async def _run():
        async def handler(request: httpx.Request):
            assert request.url.path == "/api/departures/KGX"
            assert request.url.params["limit"] == "10"
            return httpx.Response(200, json={
                "generated_at": "2026-10-05T22:00:00+01:00",
                "resolved": {"station": {"name": "KINGS CROSS LONDON", "crs": "KGX"}},
                "results": [{
                    "departs": "2026-10-05T22:10:00+01:00",
                    "expected_departs": "2026-10-05T22:14:00+01:00",
                    "train_id": "123",
                    "headcode": "1A23",
                    "status": "expected_late",
                    "status_text": "Expected 22:14",
                    "platform": "5",
                    "operator": "LNER",
                    "destination": {"name": "EDINBURGH", "crs": "EDB"},
                }],
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
        assert result.departures[0].destination == "EDINBURGH"
        assert result.departures[0].scheduled == "22:10"
        assert result.departures[0].expected == "22:14"
        assert result.departures[0].platform == "5"
    asyncio.run(_run())
