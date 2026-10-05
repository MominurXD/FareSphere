from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_provider_status_is_exposed_without_secrets():
    response = client.get("/api/v1/providers")
    assert response.status_code == 200
    providers = response.json()
    assert {item["id"] for item in providers} >= {"duffel", "tfl", "national-rail", "trainline"}
    forbidden = {"token", "api_key", "access_token", "secret", "consumer_key"}
    assert all(forbidden.isdisjoint(set(item.keys())) for item in providers)


def test_live_search_fails_closed_when_provider_not_configured():
    response = client.post(
        "/api/v1/search",
        json={
            "origin": "LON",
            "destination": "BCN",
            "departure_date": "2026-11-14",
            "passengers": 1,
            "checked_bags": 0,
            "flexible_days": 0,
            "sort": "best",
        },
    )
    assert response.status_code == 503
    assert "will not substitute sample prices" in response.json()["detail"]


def test_sample_endpoint_is_disabled_by_default():
    response = client.post(
        "/api/v1/sample/search",
        json={
            "origin": "LON",
            "destination": "BCN",
            "departure_date": "2026-11-14",
            "passengers": 1,
            "checked_bags": 0,
            "flexible_days": 2,
            "sort": "best",
        },
    )
    assert response.status_code == 404
