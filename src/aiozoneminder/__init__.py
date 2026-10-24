"""Async client for ZoneMinder, over API v3 (zm-api) or the built-in API v2."""

from __future__ import annotations

from datetime import tzinfo

import aiohttp

from .client import ZoneMinderClient, ZoneMinderLegacyClient, ZoneMinderV3Client
from .const import (
    BACKEND_LEGACY,
    BACKEND_V3,
    BACKENDS,
    DEFAULT_STREAM_MAXFPS,
    DEFAULT_TIMEOUT,
)
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
    function_fields,
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
    "function_fields",
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
    zms_path: str | None = None,
    stream_scale: int | None = None,
    stream_maxfps: float | None = DEFAULT_STREAM_MAXFPS,
) -> ZoneMinderClient:
    """Return the client for ``backend``: ``"v3"`` or ``"legacy"`` (API v2).

    ``host`` is the server URL: zm-api's address for v3 (for example
    ``http://zm.local:8080``), or ZoneMinder's web path for v2 (for example
    ``http://zm.local/zm``). ``zms_path`` says where API v2's nph-zms is,
    when finding it after login isn't wanted. ``stream_scale`` (percent) and
    ``stream_maxfps`` shrink and slow API v2's MJPEG. v3 ignores all three.
    """
    if backend not in BACKENDS:
        raise ValueError(f"Unknown backend {backend!r}; use one of {BACKENDS}")
    if backend == BACKEND_V3:
        return ZoneMinderV3Client(
            host,
            username,
            password,
            session,
            timeout=timeout,
            verify_ssl=verify_ssl,
            timezone=timezone,
        )
    return ZoneMinderLegacyClient(
        host,
        username,
        password,
        session,
        timeout=timeout,
        verify_ssl=verify_ssl,
        timezone=timezone,
        zms_path=zms_path,
        stream_scale=stream_scale,
        stream_maxfps=stream_maxfps,
    )
