from __future__ import annotations


class ProviderNotConfigured(RuntimeError):
    pass


class ProviderUnavailable(RuntimeError):
    pass


class UnsupportedLiveRequest(ValueError):
    pass
