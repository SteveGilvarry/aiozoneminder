"""Shared fixtures: an aiohttp session and a stand-in zm-api server."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
import inspect
import re
from types import SimpleNamespace
from typing import Any

import aiohttp
from aiohttp import ClientResponse
from aioresponses import CallbackResult, aioresponses, core as aioresponses_core
import pytest
from yarl import URL

from aiozoneminder import ZoneMinderV3Client

from .fixtures import (
    CONFIGS,
    EVENT_SUMMARY,
    EVENTS,
    HOST,
    LIVE_PLAYLIST,
    MONITOR_STATUS,
    MONITORS,
    RUN_STATES,
    STORAGE,
    SYSTEM_STATUS,
    VERSION_RESPONSE,
    paginated,
)

if "stream_writer" in inspect.signature(ClientResponse.__init__).parameters:
    # aiohttp 3.14 added a required argument that aioresponses 0.7.9 doesn't
    # pass. Mocked responses are already "sent", so a writer that reports
    # nothing written is all it needs.

    class _MockedResponse(ClientResponse):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("stream_writer", SimpleNamespace(output_size=0))
            super().__init__(*args, **kwargs)

    aioresponses_core.ClientResponse = _MockedResponse


def url(path: str) -> re.Pattern[str]:
    """Match a zm-api endpoint whatever its query string."""
    return re.compile(rf"^{re.escape(HOST)}/{path}(\?.*)?$")


@pytest.fixture
async def session() -> AsyncGenerator[aiohttp.ClientSession]:
    """Return an aiohttp session, closed after the test."""
    async with aiohttp.ClientSession() as client_session:
        yield client_session


@pytest.fixture
def mocked() -> Generator[aioresponses]:
    """Intercept every request, with nothing registered."""
    with aioresponses() as mock:
        yield mock


@pytest.fixture
def zm_api(mocked: aioresponses) -> aioresponses:
    """Serve a stand-in zm-api with the usual read endpoints."""
    register_zm_api(mocked)
    return mocked


@pytest.fixture
def client(session: aiohttp.ClientSession) -> ZoneMinderV3Client:
    """Return a v3 client pointed at the stand-in server."""
    return ZoneMinderV3Client(HOST, "admin", "hunter2", session)


def register_login(mocked: aioresponses, *, expire_in: int = 600) -> None:
    """Register a successful login."""
    mocked.post(
        f"{HOST}/api/v3/auth/login",
        payload={
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "token_type": "Bearer",
            "expire_in": expire_in,
        },
        repeat=True,
    )


def register_zm_api(mocked: aioresponses) -> None:
    """Register login and the collection endpoints."""
    register_login(mocked)
    mocked.get(url("api/v3/host/getVersion"), payload=VERSION_RESPONSE, repeat=True)
    mocked.get(url("api/v3/monitors"), payload=paginated(MONITORS), repeat=True)
    mocked.get(
        url("api/v3/monitor-status"), payload=paginated(MONITOR_STATUS), repeat=True
    )

    def _events(request_url: URL, **_kwargs: Any) -> CallbackResult:
        """Answer /events the way the server does, honouring the filters."""
        selected = EVENTS
        if (monitor_id := request_url.query.get("monitor_id")) is not None:
            selected = [e for e in selected if e["monitor_id"] == int(monitor_id)]
        if (start := request_url.query.get("start_time")) is not None:
            selected = [e for e in selected if e["start_date_time"] >= start]
        if (end := request_url.query.get("end_time")) is not None:
            # zm-api compares the end, so an event still recording never matches.
            selected = [
                e
                for e in selected
                if e["end_date_time"] is not None and e["end_date_time"] <= end
            ]
        selected = sorted(
            selected,
            key=lambda e: (e["start_date_time"], e["id"]),
            reverse=request_url.query.get("direction") != "asc",
        )
        limit = int(request_url.query.get("page_size", 100))
        page = int(request_url.query.get("page", 1))
        payload = paginated(selected[(page - 1) * limit : page * limit])
        payload["last_page"] = max(1, -(-len(selected) // limit))
        return CallbackResult(payload=payload)

    mocked.get(url("api/v3/events"), callback=_events, repeat=True)
    mocked.get(url(r"api/v3/event-summaries/\d+"), payload=EVENT_SUMMARY, repeat=True)
    mocked.get(url("api/v3/system/status"), payload=SYSTEM_STATUS, repeat=True)
    mocked.get(url("api/v3/storage"), payload=paginated(STORAGE), repeat=True)
    mocked.get(url("api/v3/configs"), payload=paginated(CONFIGS), repeat=True)
    mocked.get(url("api/v3/states"), payload=paginated(RUN_STATES), repeat=True)
    mocked.get(
        url("api/v3/live/\\d+/hls/live\\.m3u8"),
        body=LIVE_PLAYLIST,
        content_type="application/vnd.apple.mpegurl",
        repeat=True,
    )
