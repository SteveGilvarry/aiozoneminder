"""Fixtures for the live tests: configured backends, clients and monitors.

Clients are shared for the whole run (zm-api rate-limits logins), so the tests
and fixtures here run in one session-wide event loop.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
import contextlib
from types import SimpleNamespace

import aiohttp
import pytest
import pytest_asyncio

from aiozoneminder import BACKENDS, Monitor, ZMError, ZoneMinderClient

from .support import API_NAMES, CONFIG, client_for

NOT_CONFIGURED = (
    "live tests: set ZM_LIVE_V2_URL and/or ZM_LIVE_V3_URL, ZM_LIVE_USER and "
    "ZM_LIVE_PASSWORD to run them"
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "backends(*names): run only on these backends (v3, legacy)"
    )
    config.addinivalue_line(
        "markers", "write: changes the server; runs only with ZM_LIVE_WRITE=1"
    )
    config.addinivalue_line(
        "markers", "fixed_by(title, backends): xfail until that open PR is merged"
    )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Run each test once per configured backend it applies to."""
    if "backend" not in metafunc.fixturenames:
        return
    marker = metafunc.definition.get_closest_marker("backends")
    wanted = list(marker.args) if marker else list(BACKENDS)
    if not CONFIG.configured:
        params = [pytest.param(None, marks=pytest.mark.skip(reason=NOT_CONFIGURED))]
    else:
        params = [
            pytest.param(
                backend, id=API_NAMES[backend], marks=_known_bugs(metafunc, backend)
            )
            for backend in wanted
            if backend in CONFIG.urls
        ]
        if not params:
            needs = " or ".join(f"API {API_NAMES[b]}" for b in wanted)
            params = [
                pytest.param(None, marks=pytest.mark.skip(reason=f"needs {needs}"))
            ]
    metafunc.parametrize("backend", params)


def _known_bugs(metafunc: pytest.Metafunc, backend: str) -> list[pytest.MarkDecorator]:
    """Return xfail marks for the open PRs that fix this test on ``backend``."""
    marks = []
    for mark in metafunc.definition.iter_markers("fixed_by"):
        backends = mark.kwargs.get("backends") or BACKENDS
        if backend in backends:
            reason = f"fixed by the open PR: {mark.args[0]}"
            marks.append(pytest.mark.xfail(strict=False, reason=reason))
    return marks


def pytest_runtest_setup(item: pytest.Item) -> None:
    if item.get_closest_marker("write") and not CONFIG.write:
        pytest.skip("changes the server: set ZM_LIVE_WRITE=1 to run it")


class Clients:
    """One authenticated client per backend, and what was learnt about it."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session
        self.clients: dict[str, ZoneMinderClient] = {}
        self.monitors: dict[str, list[Monitor]] = {}

    async def get(self, backend: str) -> ZoneMinderClient:
        if backend not in self.clients:
            zm = client_for(backend, self.session)
            await zm.authenticate()
            self.clients[backend] = zm
        return self.clients[backend]

    async def all_monitors(self, backend: str) -> list[Monitor]:
        if backend not in self.monitors:
            zm = await self.get(backend)
            self.monitors[backend] = await zm.get_monitors()
        return self.monitors[backend]

    async def close(self) -> None:
        for zm in self.clients.values():
            with contextlib.suppress(ZMError):
                await zm.close()


@pytest.fixture(scope="session")
def requests_seen() -> list[str]:
    """Return the URLs requested through the shared session, in order."""
    return []


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def live_http(
    requests_seen: list[str],
) -> AsyncGenerator[aiohttp.ClientSession]:
    """Return the aiohttp session every live client shares."""

    async def record(
        _session: aiohttp.ClientSession,
        _context: SimpleNamespace,
        params: aiohttp.TraceRequestStartParams,
    ) -> None:
        requests_seen.append(str(params.url))

    trace = aiohttp.TraceConfig()
    trace.on_request_start.append(record)
    async with aiohttp.ClientSession(trace_configs=[trace]) as session:
        yield session


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def live_clients(live_http: aiohttp.ClientSession) -> AsyncGenerator[Clients]:
    """Return the shared clients, logged out at the end of the run."""
    clients = Clients(live_http)
    yield clients
    await clients.close()


@pytest_asyncio.fixture(loop_scope="session")
async def zm(backend: str, live_clients: Clients) -> ZoneMinderClient:
    """Return the shared, authenticated client for this test's backend."""
    return await live_clients.get(backend)


@pytest_asyncio.fixture(loop_scope="session")
async def monitors(backend: str, live_clients: Clients) -> list[Monitor]:
    """Return the server's monitors, as listed at the start of the run."""
    return await live_clients.all_monitors(backend)


@pytest_asyncio.fixture(loop_scope="session")
async def monitor(zm: ZoneMinderClient, monitors: list[Monitor]) -> Monitor:
    """Return the monitor to test with.

    ZM_LIVE_MONITOR if set, else the first capturing monitor, preferring one
    with PTZ control.
    """
    if CONFIG.monitor is not None:
        return await zm.get_monitor(CONFIG.monitor)
    capturing = [m for m in monitors if m.capturing != "None"]
    if not capturing:
        pytest.skip("no capturing monitor on the server")
    return next((m for m in capturing if m.controllable), capturing[0])


@pytest_asyncio.fixture(loop_scope="session")
async def recording_monitor(monitor: Monitor, monitors: list[Monitor]) -> Monitor:
    """Return a capturing monitor that records events, for forced alarms."""
    if monitor.capturing != "None" and monitor.recording != "None":
        return monitor
    found = next(
        (m for m in monitors if m.capturing != "None" and m.recording != "None"), None
    )
    if found is None:
        pytest.skip("no monitor both captures and records, so alarms leave no event")
    return found


@pytest_asyncio.fixture(loop_scope="session")
async def spare_monitor(monitor: Monitor, monitors: list[Monitor]) -> Monitor:
    """Return a capturing monitor other than the main one, if there is one.

    Tests that stop capturing use it, so the main monitor keeps running.
    """
    others = [m for m in monitors if m.capturing != "None" and m.id != monitor.id]
    return others[0] if others else monitor
