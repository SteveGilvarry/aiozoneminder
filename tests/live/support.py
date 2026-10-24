"""Configuration and helpers for the live tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
import contextlib
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import tzinfo
import os
import sys
from typing import Any
import warnings
from zoneinfo import ZoneInfo

import aiohttp
import pytest

from aiozoneminder import (
    BACKEND_LEGACY,
    BACKEND_V3,
    Event,
    Monitor,
    ZMError,
    ZoneMinderClient,
    create_client,
)

#: The pytest id of each backend, as people call the APIs.
API_NAMES = {BACKEND_LEGACY: "v2", BACKEND_V3: "v3"}
JPEG = b"\xff\xd8\xff"
#: Causes are kept short: zm-api stores 31 characters.
CAUSE = "aiozm-live"
#: Seconds between cancelling a forced alarm and the next one.
ALARM_GAP = 15


@dataclass(frozen=True)
class LiveConfig:
    """The live suite's settings, from ZM_LIVE_* environment variables."""

    urls: dict[str, str] = field(default_factory=dict)
    user: str = ""
    password: str = ""
    timezone: tzinfo | None = None
    monitor: int | None = None
    restricted_user: str = ""
    restricted_password: str = ""
    write: bool = False

    @classmethod
    def from_env(cls) -> LiveConfig:
        """Read the configuration from the environment."""
        env = os.environ
        urls = {
            backend: url
            for backend, url in (
                (BACKEND_LEGACY, env.get("ZM_LIVE_V2_URL", "")),
                (BACKEND_V3, env.get("ZM_LIVE_V3_URL", "")),
            )
            if url
        }
        zone = env.get("ZM_LIVE_TIMEZONE")
        monitor = env.get("ZM_LIVE_MONITOR")
        return cls(
            urls=urls,
            user=env.get("ZM_LIVE_USER", ""),
            password=env.get("ZM_LIVE_PASSWORD", ""),
            timezone=ZoneInfo(zone) if zone else None,
            monitor=int(monitor) if monitor else None,
            restricted_user=env.get("ZM_LIVE_RESTRICTED_USER", ""),
            restricted_password=env.get("ZM_LIVE_RESTRICTED_PASSWORD", ""),
            write=env.get("ZM_LIVE_WRITE", "") == "1",
        )

    @property
    def configured(self) -> bool:
        """Return True when there is a server and a user to test with."""
        return bool(self.urls and self.user and self.password)


CONFIG = LiveConfig.from_env()


def fixed_by(pr_title: str, *backends: str) -> pytest.MarkDecorator:
    """Mark a test that fails until the open PR ``pr_title`` is merged.

    The conftest turns this into ``xfail(strict=False)`` on ``backends``
    (every backend when none are given).
    """
    return pytest.mark.fixed_by(pr_title, backends=backends)


def client_for(
    backend: str,
    session: aiohttp.ClientSession,
    user: str | None = None,
    password: str | None = None,
    timezone: tzinfo | None = None,
) -> ZoneMinderClient:
    """Return a new, unauthenticated client for one of the configured APIs."""
    return create_client(
        backend,
        CONFIG.urls[backend],
        CONFIG.user if user is None else user,
        CONFIG.password if password is None else password,
        session,
        timezone=timezone or CONFIG.timezone,
    )


def is_jpeg(data: bytes | None) -> bool:
    """Return True for JPEG data."""
    return bool(data) and data[:3] == JPEG  # type: ignore[index]


async def until[T](
    what: str,
    check: Callable[[], Awaitable[T]],
    timeout: float = 60,
    interval: float = 2,
) -> T:
    """Poll ``check`` until it returns something truthy; fail after ``timeout``."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        result = await check()
        if result:
            return result
        if loop.time() > deadline:
            pytest.fail(f"no {what} within {timeout:.0f}s")
        await asyncio.sleep(interval)


async def wait_until_capturing(zm: ZoneMinderClient, monitor_id: int) -> None:
    """Wait until a monitor serves snapshots again, after a mode change."""

    async def snapshot() -> bool:
        return is_jpeg(await zm.async_get_snapshot(monitor_id))

    await until(f"snapshot from monitor {monitor_id}", snapshot, timeout=90, interval=3)


async def newest_event_id(zm: ZoneMinderClient, monitor_id: int) -> int:
    """Return the id of a monitor's newest event, or 0."""
    events = await zm.get_events(monitor_id=monitor_id, limit=5)
    return max((e.id for e in events), default=0)


async def wait_event_closed(zm: ZoneMinderClient, event_id: int) -> Event:
    """Wait until an event has an end, and return it."""

    async def closed() -> Event | None:
        event = await zm.get_event(event_id)
        return None if event.in_progress else event

    return await until(f"end of event {event_id}", closed, timeout=90, interval=3)


@asynccontextmanager
async def forced_alarm(
    zm: ZoneMinderClient, monitor_id: int, cause: str = CAUSE
) -> AsyncIterator[Event]:
    """Force an alarm on a monitor and yield the event it records.

    The alarm is cancelled on the way out, and the event given time to close,
    so that the next alarm records an event of its own.
    """
    last = await newest_event_id(zm, monitor_id)
    await zm.trigger_alarm(monitor_id, cause)
    try:

        async def new_event() -> Event | None:
            events = await zm.get_events(monitor_id=monitor_id, limit=5)
            return min((e for e in events if e.id > last), default=None, key=_id)

        yield await until("event after trigger_alarm", new_event, timeout=30)
    finally:
        await zm.cancel_alarm(monitor_id)
        cancelled = asyncio.get_running_loop().time()
        with contextlib.suppress(ZMError, pytest.fail.Exception):
            event = await newest_event_id(zm, monitor_id)
            if event > last:
                await wait_event_closed(zm, event)
        # An alarm inside the event's post-event frames extends it instead of
        # recording a new one, and a client that misreads open events as
        # closed can't wait for the end: leave a margin either way.
        margin = ALARM_GAP - (asyncio.get_running_loop().time() - cancelled)
        await asyncio.sleep(max(margin, 3))


def _id(event: Event) -> int:
    return event.id


Modes = tuple[str, str, str, str]


def modes_of(monitor: Monitor) -> Modes:
    """Return (capturing, analysing, recording, decoding)."""
    return (monitor.capturing, monitor.analysing, monitor.recording, monitor.decoding)


@asynccontextmanager
async def restoring_modes(
    zm: ZoneMinderClient, monitor_id: int
) -> AsyncIterator[Modes]:
    """Yield a monitor's modes, and put them back afterwards.

    The modes are read back after restoring them; a monitor that doesn't come
    back fails the test, and it waits until the monitor serves snapshots again
    if it was capturing.
    """
    original = modes_of(await zm.get_monitor(monitor_id))
    try:
        yield original
    finally:
        failing = sys.exc_info()[0] is not None
        problem = await _restore_modes(zm, monitor_id, original)
        if problem and failing:
            warnings.warn(problem, stacklevel=1)
        elif problem:
            pytest.fail(problem)


async def _restore_modes(
    zm: ZoneMinderClient, monitor_id: int, original: Modes
) -> str | None:
    """Put a monitor's modes back; return what went wrong, if anything."""
    capturing, analysing, recording, decoding = original
    for _attempt in (1, 2):
        try:
            if modes_of(await zm.get_monitor(monitor_id)) != original:
                await zm.set_monitor_state(
                    monitor_id,
                    capturing=capturing,
                    analysing=analysing,
                    recording=recording,
                    decoding=decoding,
                )
            now = modes_of(await zm.get_monitor(monitor_id))
        except ZMError as err:
            now_text = f"error {err}"
        else:
            if now == original:
                break
            now_text = str(now)
        await asyncio.sleep(3)
    else:
        return (
            f"monitor {monitor_id} not restored to {original}: {now_text}; "
            "set it back by hand"
        )
    if capturing != "None":
        try:
            await wait_until_capturing(zm, monitor_id)
        except pytest.fail.Exception as err:
            return f"monitor {monitor_id} restored, but {err}"
    return None


def mentions(data: Any, event_id: int) -> bool:
    """Return True when a pushed message is about ``event_id``."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key in ("id", "event_id", "eventId") and value == event_id:
                return True
            if mentions(value, event_id):
                return True
    elif isinstance(data, list):
        return any(mentions(item, event_id) for item in data)
    return False
