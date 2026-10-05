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


def test_octotrip_parses_sse_live_fares_inside_app():
    async def _run():
        payload = {
            "results": [{
                "airline": "Example Air",
                "flight_numbers": ["EA123"],
                "is_direct": True,
                "stops": 0,
                "total_duration_minutes": 130,
                "outbound": {
                    "departure": "LGW", "arrival": "BCN",
                    "departure_time": "08:00", "arrival_time": "10:10",
                    "departure_date": "2026-11-14", "arrival_date": "2026-11-14",
                    "duration_minutes": 130, "stops": 0,
                    "legs": [{
                        "flight_number": "EA123", "carrier": "Example Air",
                        "departure": "LGW", "arrival": "BCN",
                        "departure_time": "08:00", "arrival_time": "10:10",
                        "departure_date": "2026-11-14", "arrival_date": "2026-11-14",
                        "duration_minutes": 130,
                    }],
                },
                "price": 44.75,
                "currency": "GBP",
                "baggage": "Cabin bag included",
                "booking_url": "https://provider.example/book",
            }],
            "origin_resolved": {"iata": "LGW", "name": "Gatwick Airport", "country_code": "GB"},
            "destination_resolved": {"iata": "BCN", "name": "Barcelona Airport", "country_code": "ES"},
        }
        rpc = {
            "jsonrpc": "2.0", "id": 1,
            "result": {"content": [{"type": "text", "text": json.dumps(payload)}]},
        }
        body = f"event: message\ndata: {json.dumps(rpc)}\n\n"

        async def handler(request: httpx.Request):
            assert request.url.path == "/flights/mcp"
            assert request.headers["Accept"] == "application/json, text/event-stream"
            return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            result = await OctoTripProvider(client=client).search(SearchRequest(
                origin="LGW", destination="BCN", departure_date=date(2026, 11, 14),
                passengers=1, checked_bags=0, flexible_days=0, sort="cheapest",
            ))
        finally:
            await client.aclose()

        assert result.providers_used == ["OctoTrip Flights"]
        assert result.results[0].total_price == 44.75
        assert result.results[0].booking_url == "https://provider.example/book"
        assert result.results[0].legs[0].number == "EA123"
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


def test_national_rail_uses_huxley_without_owner_api_key():
    async def _run():
        async def handler(request: httpx.Request):
            assert request.url.path == "/departures/KGX/10"
            assert "x-apikey" not in request.headers
            return httpx.Response(200, json={
                "locationName": "London Kings Cross",
                "crs": "KGX",
                "trainServices": [{
                    "serviceID": "svc-1",
                    "operator": "LNER",
                    "destination": [{"locationName": "Edinburgh"}],
                    "std": "10:00",
                    "etd": "10:04",
                    "platform": "5",
                    "isCancelled": False,
                }],
            })

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            result = await NationalRailProvider(
                client=client,
                api_key="",
                huxley_base_url="https://huxley.example",
            ).departures("kgx")
        finally:
            await client.aclose()

        assert result.station == "KGX"
        assert "Huxley 2" in result.provider
        assert result.departures[0].destination == "Edinburgh"
        assert result.departures[0].expected == "10:04"
    asyncio.run(_run())
