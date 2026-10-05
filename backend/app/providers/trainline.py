from __future__ import annotations

from app.core.config import settings
from app.providers.base import ProviderNotConfigured, UnsupportedLiveRequest


class TrainlinePartnerProvider:
    """Contract-gated adapter boundary for Trainline Partner Solutions Global API.

    Trainline's Global API is a commercial partner product. FareSphere deliberately
    does not scrape Trainline or guess undocumented endpoints. Once official partner
    documentation/credentials are available, the implementation belongs behind this
    adapter without changing the frontend contract.
    """

    def __init__(self):
        self.base_url = settings.trainline_api_base_url
        self.token = settings.trainline_api_token

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.token)

    async def search(self, *args, **kwargs):
        if not self.configured:
            raise ProviderNotConfigured("Trainline Partner Solutions is not configured.")
        raise UnsupportedLiveRequest(
            "Trainline partner credentials are present, but this repository does not ship undocumented contract-specific request mappings. Add the official partner schema before enabling rail fare search."
        )
