"""Async client for ZoneMinder, over API v3 (zm-api) or the built-in API v2."""

from __future__ import annotations

from datetime import tzinfo

import aiohttp

from .client import ZoneMinderClient, ZoneMinderLegacyClient, ZoneMinderV3Client
from .const import BACKEND_LEGACY, BACKEND_V3, BACKENDS, DEFAULT_TIMEOUT
from .exceptions import (
    ZMApiError,
    ZMAuthenticationError,
    ZMConnectionError,
    ZMError,
    ZMNotFoundError,
    ZMNotSupportedError,
)
from .models import (
    Event,
    EventSummary,
    Monitor,
    MonitorStatus,
    RunState,
    ServerInfo,
    StorageArea,
)

__version__ = "0.1.0"

__all__ = [
    "BACKENDS",
    "BACKEND_LEGACY",
    "BACKEND_V3",
    "Event",
    "EventSummary",
    "Monitor",
    "MonitorStatus",
    "RunState",
    "ServerInfo",
    "StorageArea",
    "ZMApiError",
    "ZMAuthenticationError",
    "ZMConnectionError",
    "ZMError",
    "ZMNotFoundError",
    "ZMNotSupportedError",
    "ZoneMinderClient",
    "ZoneMinderLegacyClient",
    "ZoneMinderV3Client",
    "create_client",
]


def create_client(
    backend: str,
    host: str,
    username: str,
    password: str,
    session: aiohttp.ClientSession,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    verify_ssl: bool = True,
    timezone: tzinfo | None = None,
) -> ZoneMinderClient:
    """Return the client for ``backend``: ``"v3"`` or ``"legacy"`` (API v2).

    ``host`` is the server URL: zm-api's address for v3 (for example
    ``http://zm.local:8080``), or ZoneMinder's web path for v2 (for example
    ``http://zm.local/zm``).
    """
    if backend not in BACKENDS:
        raise ValueError(f"Unknown backend {backend!r}; use one of {BACKENDS}")
    client_class = (
        ZoneMinderV3Client if backend == BACKEND_V3 else ZoneMinderLegacyClient
    )
    return client_class(
        host,
        username,
        password,
        session,
        timeout=timeout,
        verify_ssl=verify_ssl,
        timezone=timezone,
    )
