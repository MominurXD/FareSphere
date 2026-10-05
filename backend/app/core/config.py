from __future__ import annotations

import os
from dataclasses import dataclass


def _flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "FareSphere")
    api_prefix: str = os.getenv("API_PREFIX", "/api/v1")
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

    # Live providers. Credentials stay server-side and must never be exposed to Vite.
    duffel_access_token: str = os.getenv("DUFFEL_ACCESS_TOKEN", "").strip()
    tfl_app_key: str = os.getenv("TFL_APP_KEY", "").strip()
    national_rail_api_key: str = os.getenv("NATIONAL_RAIL_API_KEY", "").strip()
    national_rail_departures_url: str = os.getenv("NATIONAL_RAIL_DEPARTURES_URL", "").strip()
    trainline_api_base_url: str = os.getenv("TRAINLINE_API_BASE_URL", "").strip()
    trainline_api_token: str = os.getenv("TRAINLINE_API_TOKEN", "").strip()

    # Disabled by default so production never substitutes simulated prices for live data.
    enable_sample_data: bool = _flag("ENABLE_SAMPLE_DATA", False)

    @property
    def allowed_origins(self) -> list[str]:
        return [self.frontend_origin]


settings = Settings()
