from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_default_live_provider_status_is_healthy_without_secrets():
    response = client.get("/api/v1/providers")
    assert response.status_code == 200
    providers = response.json()
    ids = {item["id"] for item in providers}
    assert {"octotrip", "tfl", "national-rail"}.issubset(ids)
    active = {item["id"] for item in providers if item["configured"]}
    assert {"octotrip", "tfl", "national-rail"}.issubset(active)

    forbidden = {"token", "api_key", "access_token", "secret", "consumer_key"}
    assert all(forbidden.isdisjoint(set(item.keys())) for item in providers)


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
