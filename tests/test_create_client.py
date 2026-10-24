"""Tests for choosing a client."""

from __future__ import annotations

import aiohttp
import pytest

from aiozoneminder import (
    BACKEND_LEGACY,
    BACKEND_V3,
    ZoneMinderLegacyClient,
    ZoneMinderV3Client,
    create_client,
)


@pytest.mark.parametrize(
    ("backend", "expected"),
    [(BACKEND_V3, ZoneMinderV3Client), (BACKEND_LEGACY, ZoneMinderLegacyClient)],
)
async def test_picks_the_client(
    session: aiohttp.ClientSession, backend: str, expected: type
) -> None:
    client = create_client(backend, "http://zm.local/", "admin", "pw", session)
    assert type(client) is expected
    assert client.backend == backend
    # The trailing slash is dropped so paths join cleanly.
    assert client.host == "http://zm.local"


async def test_rejects_an_unknown_backend(session: aiohttp.ClientSession) -> None:
    with pytest.raises(ValueError, match="v4"):
        create_client("v4", "http://zm.local", "admin", "pw", session)


async def test_zms_path_reaches_api_v2(session: aiohttp.ClientSession) -> None:
    """API v2 streams from nph-zms; zm-api serves its own streams and ignores it."""
    v2 = create_client(
        BACKEND_LEGACY,
        "http://zm.local/zm",
        "admin",
        "pw",
        session,
        zms_path="/cgi-bin-zm/nph-zms",
    )
    v3 = create_client(
        BACKEND_V3, "http://zm.local:8080", "admin", "pw", session, zms_path="/x"
    )
    assert v2.get_stream_url(1).startswith("http://zm.local/cgi-bin-zm/nph-zms?")
    assert type(v3) is ZoneMinderV3Client


async def test_stream_options_reach_api_v2(session: aiohttp.ClientSession) -> None:
    client = create_client(
        BACKEND_LEGACY,
        "http://zm.local/zm",
        "admin",
        "pw",
        session,
        stream_scale=50,
        stream_maxfps=5,
    )
    assert "scale=50" in client.get_stream_url(1)
    assert "maxfps=5" in client.get_stream_url(1)
