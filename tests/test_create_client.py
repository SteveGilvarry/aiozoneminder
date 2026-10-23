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
