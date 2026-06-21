"""Shared package — modules used by both bot (src/) and web panel (web/backend/)."""

from shared.internal_api import BaseInternalApiClient, DirectInternalApiClient, ProxyInternalApiClient, internal_api_client

__all__ = [
    "BaseInternalApiClient",
    "DirectInternalApiClient",
    "ProxyInternalApiClient",
    "internal_api_client",
]
