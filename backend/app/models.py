from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


Mode = Literal["flight", "train", "coach", "metro", "walk"]
SortMode = Literal["cheapest", "fastest", "best"]
DataMode = Literal["live", "sample"]
ProviderKind = Literal["flights", "rail", "transit", "rail-commerce"]


class Place(BaseModel):
    code: str
    name: str
    country: str
    lat: float | None = None
    lon: float | None = None
    kind: Literal["city", "airport", "station"] = "city"


class SearchRequest(BaseModel):
    # Three-letter IATA/CRS codes remain supported, but rail station names and
    # groups such as "London Paddington" / "Manchester" are also accepted.
    origin: str = Field(min_length=2, max_length=64)
    destination: str = Field(min_length=2, max_length=64)
    departure_date: date
    departure_time: str = Field(default="09:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    passengers: int = Field(default=1, ge=1, le=9)
    checked_bags: int = Field(default=0, ge=0, le=9)
    flexible_days: int = Field(default=0, ge=0, le=7)
    sort: SortMode = "best"


class Leg(BaseModel):
    mode: Mode
    carrier: str
    number: str | None = None
    origin: Place
    destination: Place
    depart_at: datetime
    arrive_at: datetime
    ticket_price: float | None
    currency: str = "GBP"
    baggage_price: float = 0
    transfer_price: float = 0
    emissions_kg: float | None = None
    self_transfer: bool = False
    price_verified: bool = True
    source: str
    status: str | None = None
    platform: str | None = None


class Journey(BaseModel):
    id: str
    label: str
    legs: list[Leg]
    total_price: float | None
    currency: str = "GBP"
    total_duration_minutes: int
    total_emissions_kg: float | None = None
    risk_score: int
    savings_vs_baseline: float | None = None
    badges: list[str]
    score: float
    price_verified: bool
    source: str
    source_offer_id: str | None = None
    booking_url: str | None = None


class SearchResponse(BaseModel):
    origin: Place
    destination: Place
    baseline_price: float | None
    currency: str = "GBP"
    results: list[Journey]
    flexible_date_savings: list[dict[str, Any]]
    generated_at: datetime
    data_mode: DataMode
    providers_used: list[str]
    notice: str | None = None


class PriceAlertRequest(BaseModel):
    origin: str
    destination: str
    target_price: float
    email: str


class ProviderStatus(BaseModel):
    id: str
    name: str
    kind: ProviderKind
    configured: bool
    supports_live_data: bool
    purpose: str
    setup_hint: str | None = None


class NetworkPoint(BaseModel):
    name: str
    id: str | None = None
    lat: float
    lon: float


class NetworkPath(BaseModel):
    id: str
    name: str
    mode: str
    color: str
    points: list[NetworkPoint]


class NetworkResponse(BaseModel):
    provider: str
    generated_at: datetime
    paths: list[NetworkPath]
    data_mode: Literal["live"] = "live"


class Departure(BaseModel):
    service_id: str | None = None
    operator: str | None = None
    destination: str
    scheduled: str | None = None
    expected: str | None = None
    platform: str | None = None
    cancelled: bool = False


class DeparturesResponse(BaseModel):
    provider: str
    station: str
    generated_at: datetime
    departures: list[Departure]
    data_mode: Literal["live"] = "live"
