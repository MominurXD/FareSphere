from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.models import NetworkPath, NetworkPoint, NetworkResponse
from app.providers.base import ProviderNotConfigured, ProviderUnavailable


TFL_API = "https://api.tfl.gov.uk"
LINE_COLORS = {
    "bakerloo": "#B36305",
    "central": "#E32017",
    "circle": "#FFD300",
    "district": "#00782A",
    "hammersmith-city": "#F3A9BB",
    "jubilee": "#A0A5A9",
    "metropolitan": "#9B0056",
    "northern": "#000000",
    "piccadilly": "#003688",
    "victoria": "#0098D4",
    "waterloo-city": "#95CDBA",
    "elizabeth": "#6950A1",
    "dlr": "#00A4A7",
    "lioness": "#F4A71D",
    "mildmay": "#006FE6",
    "windrush": "#DC241F",
    "weaver": "#823A62",
    "suffragette": "#18A95D",
    "liberty": "#5D6061",
}


class TfLProvider:
    def __init__(self, client: httpx.AsyncClient | None = None, app_key: str | None = None):
        self._client = client
        self.app_key = settings.tfl_app_key if app_key is None else app_key

    def _params(self) -> dict[str, str]:
        if not self.app_key:
            raise ProviderNotConfigured("TfL provider is not configured.")
        return {"app_key": self.app_key}

    async def _get(self, path: str):
        owns = self._client is None
        client = self._client or httpx.AsyncClient(timeout=15.0)
        try:
            response = await client.get(f"{TFL_API}{path}", params=self._params())
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"TfL request failed: {exc}") from exc
        finally:
            if owns:
                await client.aclose()

    async def network(self) -> NetworkResponse:
        lines = await self._get("/Line/Mode/tube,overground,elizabeth-line,dlr")
        line_ids = [item.get("id") for item in lines if item.get("id")]

        async def load(line_id: str):
            try:
                return line_id, await self._get(f"/Line/{line_id}/Route/Sequence/all")
            except ProviderUnavailable:
                return line_id, None

        sequences = await asyncio.gather(*(load(line_id) for line_id in line_ids))
        paths: list[NetworkPath] = []

        for line_id, payload in sequences:
            if not payload:
                continue
            line_name = payload.get("lineName") or line_id.replace("-", " ").title()
            stop_sequences = payload.get("stopPointSequences") or []
            for index, sequence in enumerate(stop_sequences):
                raw_points = sequence.get("stopPoint") or sequence.get("stopPoints") or []
                points: list[NetworkPoint] = []
                for point in raw_points:
                    lat = point.get("lat")
                    lon = point.get("lon")
                    if lat is None or lon is None:
                        continue
                    points.append(
                        NetworkPoint(
                            id=point.get("id"),
                            name=point.get("name") or point.get("commonName") or "Stop",
                            lat=float(lat),
                            lon=float(lon),
                        )
                    )
                if len(points) >= 2:
                    paths.append(
                        NetworkPath(
                            id=f"{line_id}-{index}",
                            name=line_name,
                            mode="rail",
                            color=LINE_COLORS.get(line_id, "#6EE7FF"),
                            points=points,
                        )
                    )

        return NetworkResponse(
            provider="Transport for London Unified API",
            generated_at=datetime.now(timezone.utc),
            paths=paths,
        )
