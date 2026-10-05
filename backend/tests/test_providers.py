from datetime import date

import httpx
import asyncio

from app.models import SearchRequest
from app.providers.duffel import DuffelProvider
from app.providers.national_rail import NationalRailProvider
from app.providers.tfl import TfLProvider


def test_duffel_parses_live_offer_without_guessing_price():
    async def _run():
        async def handler(request: httpx.Request):
            assert request.url.path == "/air/offer_requests"
            assert request.headers["Authorization"] == "Bearer test-token"
            return httpx.Response(
                200,
                json={
                    "data": {
                        "offers": [
                            {
                                "id": "off_123",
                                "total_amount": "84.70",
                                "total_currency": "GBP",
                                "total_emissions_kg": "118.4",
                                "slices": [
                                    {
                                        "segments": [
                                            {
                                                "departing_at": "2026-11-14T08:00:00+00:00",
                                                "arriving_at": "2026-11-14T10:10:00+00:00",
                                                "origin": {"iata_code": "LGW", "name": "Gatwick Airport", "iata_country_code": "GB", "latitude": 51.1537, "longitude": -0.1821},
                                                "destination": {"iata_code": "BCN", "name": "Barcelona Airport", "iata_country_code": "ES", "latitude": 41.2974, "longitude": 2.0833},
                                                "operating_carrier": {"name": "Example Carrier", "iata_code": "EX"},
                                                "marketing_carrier": {"name": "Example Carrier", "iata_code": "EX"},
                                                "marketing_carrier_flight_number": "412",
                                            }
                                        ]
                                    }
                                ],
                            }
                        ]
                    }
                },
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.duffel.com")
        try:
            provider = DuffelProvider(client=client, token="test-token")
            result = await provider.search(
                SearchRequest(
                    origin="LGW", destination="BCN", departure_date=date(2026, 11, 14),
                    passengers=1, checked_bags=0, flexible_days=0, sort="cheapest",
                )
            )
        finally:
            await client.aclose()

        assert result.data_mode == "live"
        assert result.providers_used == ["Duffel"]
        assert result.results[0].price_verified is True
        assert result.results[0].total_price == 84.70
        assert result.results[0].source_offer_id == "off_123"
        assert result.results[0].legs[0].number == "EX412"

    asyncio.run(_run())


def test_tfl_network_parses_real_line_shape_without_key():
    async def _run():
        async def handler(request: httpx.Request):
            assert "app_key" not in request.url.params
            if request.url.path == "/Line/Mode/tube,overground,elizabeth-line,dlr":
                return httpx.Response(200, json=[{"id": "central", "name": "Central"}])
            if request.url.path == "/Line/central/Route/Sequence/all":
                return httpx.Response(
                    200,
                    json={
                        "lineName": "Central",
                        "stopPointSequences": [
                            {
                                "stopPoint": [
                                    {"id": "940GZZLUEBY", "name": "Ealing Broadway", "lat": 51.5152, "lon": -0.3017},
                                    {"id": "940GZZLUADE", "name": "North Acton", "lat": 51.5237, "lon": -0.2597},
                                ]
                            }
                        ],
                    },
                )
            return httpx.Response(404)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.tfl.gov.uk")
        try:
            result = await TfLProvider(client=client, app_key="").network()
        finally:
            await client.aclose()

        assert result.data_mode == "live"
        assert result.provider.startswith("Transport for London")
        assert result.paths[0].name == "Central"
        assert result.paths[0].color == "#E32017"
        assert len(result.paths[0].points) == 2

    asyncio.run(_run())


def test_tfl_adds_key_when_configured():
    async def _run():
        async def handler(request: httpx.Request):
            assert request.url.params.get("app_key") == "test-key"
            if request.url.path == "/Line/Mode/tube,overground,elizabeth-line,dlr":
                return httpx.Response(200, json=[{"id": "central"}])
            return httpx.Response(
                200,
                json={
                    "lineName": "Central",
                    "stopPointSequences": [{"stopPoint": [
                        {"id": "a", "name": "A", "lat": 51.5, "lon": -0.2},
                        {"id": "b", "name": "B", "lat": 51.51, "lon": -0.1},
                    ]}],
                },
            )
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.tfl.gov.uk")
        try:
            await TfLProvider(client=client, app_key="test-key").network()
        finally:
            await client.aclose()
    asyncio.run(_run())


def test_national_rail_parses_live_departure_board():
    async def _run():
        async def handler(request: httpx.Request):
            assert request.headers["x-apikey"] == "rail-key"
            return httpx.Response(
                200,
                json={
                    "trainServices": [
                        {
                            "serviceID": "svc-1",
                            "operator": "LNER",
                            "destination": [{"locationName": "Edinburgh"}],
                            "std": "10:00",
                            "etd": "10:04",
                            "platform": "5",
                            "isCancelled": False,
                        }
                    ]
                },
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://rail.example")
        try:
            result = await NationalRailProvider(
                client=client,
                api_key="rail-key",
                endpoint_template="https://rail.example/board/{crs}",
            ).departures("kgx")
        finally:
            await client.aclose()

        assert result.data_mode == "live"
        assert result.station == "KGX"
        assert result.departures[0].destination == "Edinburgh"
        assert result.departures[0].expected == "10:04"
        assert result.departures[0].platform == "5"
    asyncio.run(_run())
