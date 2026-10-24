"""Tests for the API v3 (zm-api) client."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Any

import aiohttp
from aioresponses import aioresponses
import pytest
from yarl import URL

from aiozoneminder import (
    RunState,
    ZMApiError,
    ZMAuthenticationError,
    ZMConnectionError,
    ZMNotFoundError,
    ZMNotSupportedError,
    ZoneMinderV3Client,
)

from .conftest import register_login, url
from .fixtures import HOST, RUN_STATES, monitor, paginated


def calls(mocked: aioresponses, method: str, path: str) -> list[Any]:
    """Return the recorded calls to one endpoint, whatever their query."""
    found = []
    for (verb, called), requests in mocked.requests.items():
        if verb == method and str(called).split("?")[0] == f"{HOST}/{path}":
            found.extend(requests)
    return found


def bearer(call: Any) -> str | None:
    """Return the Authorization header a recorded call carried."""
    return (call.kwargs.get("headers") or {}).get("Authorization")


# -- Logging in ---------------------------------------------------------------


async def test_authenticate_stores_the_token(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    assert await client.authenticate() is True
    assert client.authenticated
    assert client.access_token == "access-token"
    (login,) = calls(mocked, "POST", "api/v3/auth/login")
    assert login.kwargs["json"] == {"username": "admin", "password": "hunter2"}


@pytest.mark.parametrize("status", [400, 401, 403])
async def test_bad_credentials(
    client: ZoneMinderV3Client, mocked: aioresponses, status: int
) -> None:
    mocked.post(f"{HOST}/api/v3/auth/login", status=status)
    with pytest.raises(ZMAuthenticationError):
        await client.authenticate()


async def test_no_zm_api_suggests_api_v2(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    mocked.post(f"{HOST}/api/v3/auth/login", status=404)
    with pytest.raises(ZMConnectionError, match="API v2"):
        await client.authenticate()


async def test_unreachable_server(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    mocked.post(
        f"{HOST}/api/v3/auth/login", exception=aiohttp.ClientConnectionError("down")
    )
    with pytest.raises(ZMConnectionError):
        await client.authenticate()


async def test_login_without_a_token_is_refused(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    mocked.post(f"{HOST}/api/v3/auth/login", payload={"token_type": "Bearer"})
    with pytest.raises(ZMAuthenticationError):
        await client.authenticate()


async def test_first_request_logs_in(
    client: ZoneMinderV3Client, zm_api: aioresponses
) -> None:
    assert await client.get_version() == "1.39.22"
    (version,) = calls(zm_api, "GET", "api/v3/host/getVersion")
    assert bearer(version) == "Bearer access-token"


async def test_expired_token_is_refreshed_and_retried(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    mocked.get(url("api/v3/host/getVersion"), status=401)
    mocked.post(
        f"{HOST}/api/v3/auth/refresh",
        payload={"access_token": "fresh-token", "expire_in": 600},
    )
    mocked.get(url("api/v3/host/getVersion"), payload={"version": "1.39.41"})

    assert await client.get_version() == "1.39.41"
    (refresh,) = calls(mocked, "POST", "api/v3/auth/refresh")
    assert refresh.kwargs["json"] == {"token": "refresh-token"}
    assert bearer(calls(mocked, "GET", "api/v3/host/getVersion")[-1]) == (
        "Bearer fresh-token"
    )


async def test_failed_refresh_logs_in_again(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    mocked.get(url("api/v3/host/getVersion"), status=401)
    mocked.post(f"{HOST}/api/v3/auth/refresh", status=401)
    mocked.get(url("api/v3/host/getVersion"), payload={"version": "1.39.41"})

    assert await client.get_version() == "1.39.41"
    assert len(calls(mocked, "POST", "api/v3/auth/login")) == 2


async def test_two_rejections_give_up(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    mocked.get(url("api/v3/host/getVersion"), status=401, repeat=True)
    mocked.post(f"{HOST}/api/v3/auth/refresh", status=401, repeat=True)
    with pytest.raises(ZMAuthenticationError):
        await client.get_version()


async def test_token_near_expiry_is_refreshed_first(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    # Expiring within the 60 second margin counts as expired.
    register_login(mocked, expire_in=30)
    mocked.post(
        f"{HOST}/api/v3/auth/refresh",
        payload={"access_token": "fresh-token", "expire_in": 600},
    )
    mocked.get(url("api/v3/host/getVersion"), payload={"version": "1.39.41"})

    await client.authenticate()
    await client.get_version()
    assert len(calls(mocked, "POST", "api/v3/auth/refresh")) == 1
    assert client.access_token == "fresh-token"


async def test_close_forgets_the_session(
    client: ZoneMinderV3Client, zm_api: aioresponses
) -> None:
    await client.authenticate()
    await client.close()
    assert not client.authenticated
    assert client.access_token is None


# -- Errors -------------------------------------------------------------------


async def test_not_found(client: ZoneMinderV3Client, mocked: aioresponses) -> None:
    register_login(mocked)
    mocked.get(url("api/v3/monitors/9"), status=404)
    with pytest.raises(ZMNotFoundError):
        await client.get_monitor(9)


async def test_server_error(client: ZoneMinderV3Client, mocked: aioresponses) -> None:
    register_login(mocked)
    mocked.get(url("api/v3/monitors/1"), status=500)
    with pytest.raises(ZMApiError, match="500"):
        await client.get_monitor(1)


async def test_dropped_connection(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    mocked.get(url("api/v3/monitors/1"), exception=aiohttp.ServerDisconnectedError())
    with pytest.raises(ZMConnectionError):
        await client.get_monitor(1)


# -- Server -------------------------------------------------------------------


async def test_server_info(client: ZoneMinderV3Client, zm_api: aioresponses) -> None:
    info = await client.get_server_info()
    assert info.version == "1.39.22"
    assert info.api_version == "3.0.0-alpha.1"
    assert info.running is True
    assert (info.daemons_running, info.daemons_total) == (2, 3)
    assert info.total_disk_space == 51762574243


async def test_server_info_survives_missing_extras(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    mocked.get(url("api/v3/host/getVersion"), payload={"version": "1.39.41"})
    mocked.get(url("api/v3/system/status"), status=500)
    mocked.get(url("api/v3/storage"), status=404)

    info = await client.get_server_info()
    assert info.version == "1.39.41"
    assert info.daemons_total == 0
    assert info.storage == []


async def test_configs(client: ZoneMinderV3Client, zm_api: aioresponses) -> None:
    configs = await client.get_configs()
    assert configs["ZM_MQTT_TOPIC_PREFIX"] == "ZoneMinder"
    assert configs["ZM_MQTT_HOSTNAME"] == "192.168.0.66"


# -- Monitors -----------------------------------------------------------------


async def test_monitors(client: ZoneMinderV3Client, zm_api: aioresponses) -> None:
    monitors = await client.get_monitors()
    assert [m.name for m in monitors] == ["Driveway", "Back door", "Gate"]
    assert monitors[2].controllable is True


async def test_every_page_is_read(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    first = {**paginated([monitor(1, "One")]), "last_page": 2}
    second = {**paginated([monitor(2, "Two")]), "current_page": 2, "last_page": 2}
    mocked.get(url("api/v3/monitors"), payload=first)
    mocked.get(url("api/v3/monitors"), payload=second)

    assert [m.name for m in await client.get_monitors()] == ["One", "Two"]
    pages = [
        c.kwargs["params"]["page"] for c in calls(mocked, "GET", "api/v3/monitors")
    ]
    assert pages == [1, 2]


async def test_deleted_and_broken_monitors_are_skipped(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    deleted = {**monitor(2, "Gone"), "deleted": True}
    broken = {"id": "not a number"}
    mocked.get(
        url("api/v3/monitors"),
        payload=paginated([monitor(1, "Kept"), deleted, broken]),
    )
    assert [m.name for m in await client.get_monitors()] == ["Kept"]


async def test_monitor_statuses(
    client: ZoneMinderV3Client, zm_api: aioresponses
) -> None:
    statuses = await client.get_monitor_statuses()
    assert set(statuses) == {1, 2, 3}
    assert statuses[2].analysis_fps == pytest.approx(9.8)


async def test_monitor_statuses_unavailable(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    mocked.get(url("api/v3/monitor-status"), status=404)
    assert await client.get_monitor_statuses() == {}


async def test_set_monitor_state_sends_only_what_changes(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    mocked.patch(url("api/v3/monitors/2"), payload={})

    await client.set_monitor_state(2, analysing="Always", recording="OnMotion")
    await client.set_monitor_state(2)  # Nothing to change: no request.

    (patch,) = calls(mocked, "PATCH", "api/v3/monitors/2")
    assert patch.kwargs["json"] == {"analysing": "Always", "recording": "OnMotion"}


# -- Events -------------------------------------------------------------------


async def test_events(client: ZoneMinderV3Client, zm_api: aioresponses) -> None:
    events = await client.get_events(monitor_id=2, limit=10)
    assert [e.id for e in events] == [298, 297]
    params = calls(zm_api, "GET", "api/v3/events")[0].kwargs["params"]
    assert params["sort"] == "start_time"
    assert params["direction"] == "desc"
    assert params["page_size"] == 10


async def test_events_between_sends_utc(
    client: ZoneMinderV3Client, zm_api: aioresponses
) -> None:
    start = datetime(2026, 8, 22, 23, 0, tzinfo=UTC)
    end = datetime(2026, 8, 23, 1, 0, tzinfo=UTC)
    await client.get_events_between(1, start, end)
    params = calls(zm_api, "GET", "api/v3/events")[0].kwargs["params"]
    assert params["start_time"] == "2026-08-22T23:00:00Z"
    assert params["end_time"] == "2026-08-23T01:00:00Z"
    assert params["monitor_id"] == 1


async def test_one_event(client: ZoneMinderV3Client, mocked: aioresponses) -> None:
    from .fixtures import event

    register_login(mocked)
    mocked.get(url("api/v3/events/298"), payload=event(298, 2, alarm_frames=3))
    found = await client.get_event(298)
    assert found.monitor_id == 2
    assert found.is_alarm


async def test_event_summary(client: ZoneMinderV3Client, zm_api: aioresponses) -> None:
    summary = await client.get_event_summary(1)
    assert summary is not None
    assert summary.day_events == 85


async def test_camera_without_events_has_a_zero_summary(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    mocked.get(url("api/v3/event-summaries/4"), status=404)
    summary = await client.get_event_summary(4)
    assert summary is not None
    assert summary.total_events == 0


async def test_event_summary_failure(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    mocked.get(url("api/v3/event-summaries/1"), status=500)
    assert await client.get_event_summary(1) is None


# -- Run states ---------------------------------------------------------------


async def test_run_states(client: ZoneMinderV3Client, zm_api: aioresponses) -> None:
    states = await client.get_run_states()
    assert [s.name for s in states] == ["default", "Home", "Away"]
    assert next(s for s in states if s.active).name == "Home"


async def test_saving_a_new_run_state_creates_it(
    client: ZoneMinderV3Client, zm_api: aioresponses
) -> None:
    zm_api.post(url("api/v3/states"), payload={})
    await client.save_run_state("Holiday", "1:Always:Always:Always")
    (post,) = calls(zm_api, "POST", "api/v3/states")
    assert post.kwargs["json"] == {
        "name": "Holiday",
        "definition": "1:Always:Always:Always",
    }


async def test_saving_an_existing_run_state_overwrites_it(
    client: ZoneMinderV3Client, zm_api: aioresponses
) -> None:
    zm_api.patch(url("api/v3/states/3"), payload={})
    await client.save_run_state("Away", "1:Always:None:None")
    (patch,) = calls(zm_api, "PATCH", "api/v3/states/3")
    assert patch.kwargs["json"] == {"definition": "1:Always:None:None"}


async def test_switching_run_state(
    client: ZoneMinderV3Client, zm_api: aioresponses
) -> None:
    for monitor_id in (1, 2, 3):
        zm_api.patch(url(f"api/v3/monitors/{monitor_id}"), payload={})
    for state_id in (2, 3):
        zm_api.patch(url(f"api/v3/states/{state_id}"), payload={})

    away = RunState.from_dict(RUN_STATES[2])
    await client.set_run_state(away)

    # Cameras 1 and 3 differ from Away. Camera 2 already matches, so it's
    # left alone.
    assert calls(zm_api, "PATCH", "api/v3/monitors/1")[0].kwargs["json"] == {
        "capturing": "Always",
        "analysing": "Always",
        "recording": "Always",
    }
    assert len(calls(zm_api, "PATCH", "api/v3/monitors/3")) == 1
    assert calls(zm_api, "PATCH", "api/v3/monitors/2") == []
    # Home stops being active and Away starts. "default" was already off.
    assert calls(zm_api, "PATCH", "api/v3/states/2")[0].kwargs["json"] == {
        "is_active": 0
    }
    assert calls(zm_api, "PATCH", "api/v3/states/3")[0].kwargs["json"] == {
        "is_active": 1
    }
    assert calls(zm_api, "PATCH", "api/v3/states/1") == []


# -- Alarms and PTZ -----------------------------------------------------------


async def test_alarms(client: ZoneMinderV3Client, mocked: aioresponses) -> None:
    register_login(mocked)
    mocked.patch(url("api/v3/monitors/1/alarm"), payload={}, repeat=True)

    await client.trigger_alarm(1, "Doorbell")
    await client.cancel_alarm(1)

    on, off = calls(mocked, "PATCH", "api/v3/monitors/1/alarm")
    assert on.kwargs["json"] == {"action": "on", "cause": "Doorbell"}
    assert off.kwargs["json"] == {"action": "off"}


@pytest.mark.parametrize(
    ("command", "kwargs", "path"),
    [
        ("up-left", {}, "move/up-left"),
        ("stop", {}, "move/stop"),
        ("zoom-in", {}, "zoom/in"),
        ("focus-auto", {}, "focus/auto"),
        ("home", {}, "home"),
        ("preset", {"preset": 2}, "presets/2/goto"),
    ],
)
async def test_ptz_commands(
    client: ZoneMinderV3Client,
    mocked: aioresponses,
    command: str,
    kwargs: dict[str, Any],
    path: str,
) -> None:
    register_login(mocked)
    mocked.post(url(f"api/v3/ptz/monitors/3/{path}"), payload={})
    await client.ptz(3, command, **kwargs)
    assert len(calls(mocked, "POST", f"api/v3/ptz/monitors/3/{path}")) == 1


async def test_ptz_preset_needs_a_number(
    client: ZoneMinderV3Client, zm_api: aioresponses
) -> None:
    with pytest.raises(ZMApiError, match="preset number"):
        await client.ptz(3, "preset")


async def test_unknown_ptz_command(
    client: ZoneMinderV3Client, zm_api: aioresponses
) -> None:
    with pytest.raises(ZMNotSupportedError):
        await client.ptz(3, "spin")


async def test_ptz_presets_are_for_one_camera(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    mocked.get(
        url("api/v3/control_presets"),
        payload=paginated(
            [
                {"monitor_id": 3, "preset": 1, "label": "Front gate"},
                {"monitor_id": 3, "preset": 2, "label": None},
                {"monitor_id": 4, "preset": 1, "label": "Elsewhere"},
            ]
        ),
    )
    assert await client.get_ptz_presets(3) == {1: "Front gate", 2: "Preset 2"}


async def test_ptz_presets_unavailable(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    mocked.get(url("api/v3/control_presets"), status=404)
    assert await client.get_ptz_presets(3) == {}


# -- Event stream -------------------------------------------------------------

STREAM = (
    ": connected\n"
    "\n"
    "id: 300\n"
    "event: event_start\n"
    'data: {"type": "event_start", "event_id": 300, "monitor_id": 1}\n'
    "\n"
    ": heartbeat\n"
    "\n"
    "event: alarm_state\n"
    'data: {"monitor_id": 2,\n'
    'data:  "state": "alarm"}\n'
    "\n"
    "data: not json\n"
    "\n"
)


async def test_event_stream(client: ZoneMinderV3Client, mocked: aioresponses) -> None:
    register_login(mocked)
    mocked.get(url("api/v3/events/stream"), body=STREAM)

    received = [message async for message in client.async_event_stream(since=299)]

    assert received == [
        ("event_start", {"type": "event_start", "event_id": 300, "monitor_id": 1}),
        # No "type" in the data, so the event: line names it.
        ("alarm_state", {"monitor_id": 2, "state": "alarm"}),
    ]
    (request,) = calls(mocked, "GET", "api/v3/events/stream")
    assert request.kwargs["params"] == {"since": "299"}
    assert request.kwargs["headers"]["Accept"] == "text/event-stream"
    assert bearer(request) == "Bearer access-token"


@pytest.mark.parametrize("status", [400, 404, 405, 422])
async def test_server_without_an_event_stream(
    client: ZoneMinderV3Client, mocked: aioresponses, status: int
) -> None:
    register_login(mocked)
    mocked.get(url("api/v3/events/stream"), status=status)
    with pytest.raises(ZMNotFoundError):
        async for _message in client.async_event_stream():
            pass


async def test_event_stream_refused(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    mocked.get(url("api/v3/events/stream"), status=401)
    with pytest.raises(ZMAuthenticationError):
        async for _message in client.async_event_stream():
            pass


# -- WebRTC (WHEP) ------------------------------------------------------------

WHEP = "api/v3/live/1/webrtc/whep"
SESSION = "/api/v3/live/1/webrtc/whep/abc123"


@pytest.mark.parametrize(
    ("status", "supported"), [(415, True), (400, True), (404, False)]
)
async def test_whep_probe(
    client: ZoneMinderV3Client, mocked: aioresponses, status: int, supported: bool
) -> None:
    register_login(mocked)
    mocked.post(url(WHEP), status=status)
    assert await client.async_supports_whep(1) is supported
    # The answer is remembered.
    assert await client.async_supports_whep(1) is supported
    assert len(calls(mocked, "POST", WHEP)) == 1


async def test_whep_probe_unreachable(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    mocked.post(url(WHEP), exception=aiohttp.ClientConnectionError())
    assert await client.async_supports_whep(1) is False


async def test_whep_offer(client: ZoneMinderV3Client, mocked: aioresponses) -> None:
    register_login(mocked)
    mocked.post(
        url(WHEP),
        status=201,
        body="v=0\r\nanswer",
        headers={"Location": SESSION},
        content_type="application/sdp",
    )

    answer, location = await client.async_whep_offer(1, "v=0\r\noffer")

    assert answer == "v=0\r\nanswer"
    assert location == SESSION
    (offer,) = calls(mocked, "POST", WHEP)
    assert offer.kwargs["data"] == b"v=0\r\noffer"
    assert offer.kwargs["headers"]["Content-Type"] == "application/sdp"


@pytest.mark.parametrize(
    ("status", "message"),
    [(406, "codec"), (503, "session limit"), (418, "teapot")],
)
async def test_whep_offer_refused(
    client: ZoneMinderV3Client, mocked: aioresponses, status: int, message: str
) -> None:
    register_login(mocked)
    mocked.post(url(WHEP), status=status, body="I'm a teapot")
    with pytest.raises(ZMApiError, match=message):
        await client.async_whep_offer(1, "v=0")


async def test_whep_answer_without_a_session(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    mocked.post(url(WHEP), status=201, body="v=0")
    with pytest.raises(ZMApiError, match="location"):
        await client.async_whep_offer(1, "v=0")


async def test_whep_offer_unreachable(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    mocked.post(url(WHEP), exception=aiohttp.ClientConnectionError())
    with pytest.raises(ZMConnectionError):
        await client.async_whep_offer(1, "v=0")


async def test_whep_candidate(client: ZoneMinderV3Client, mocked: aioresponses) -> None:
    register_login(mocked)
    mocked.patch(f"{HOST}{SESSION}", status=204, repeat=True)

    await client.async_whep_candidate(
        SESSION, "0", "candidate:1 1 udp 1 10.0.0.2 5 typ host"
    )
    await client.async_whep_candidate(SESSION, None, "a=end-of-candidates")

    first, second = calls(mocked, "PATCH", SESSION.lstrip("/"))
    assert first.kwargs["data"] == (
        b"a=mid:0\r\na=candidate:1 1 udp 1 10.0.0.2 5 typ host\r\n"
    )
    assert first.kwargs["headers"]["Content-Type"] == "application/trickle-ice-sdpfrag"
    assert second.kwargs["data"] == b"a=end-of-candidates\r\n"


async def test_whep_candidate_unreachable(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    mocked.patch(f"{HOST}{SESSION}", exception=aiohttp.ClientConnectionError())
    with pytest.raises(ZMConnectionError):
        await client.async_whep_candidate(SESSION, "0", "candidate:1")


async def test_whep_session_at_an_absolute_url(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    elsewhere = "https://media.example/whep/abc123"
    mocked.patch(elsewhere, status=204)
    mocked.delete(elsewhere, status=200)

    await client.async_whep_candidate(elsewhere, "0", "candidate:1")
    await client.async_whep_close(elsewhere)

    assert ("PATCH", URL(elsewhere)) in mocked.requests
    assert ("DELETE", URL(elsewhere)) in mocked.requests


async def test_whep_close(client: ZoneMinderV3Client, mocked: aioresponses) -> None:
    register_login(mocked)
    await client.authenticate()
    mocked.delete(f"{HOST}{SESSION}", status=200)
    await client.async_whep_close(SESSION)
    (close,) = calls(mocked, "DELETE", SESSION.lstrip("/"))
    assert bearer(close) == "Bearer access-token"


async def test_whep_close_tolerates_a_dead_server(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    mocked.delete(f"{HOST}{SESSION}", exception=aiohttp.ClientConnectionError())
    await client.async_whep_close(SESSION)


# -- Live video and media -----------------------------------------------------


async def test_rtsp_link_is_reused(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    expires = datetime(2099, 1, 1, tzinfo=UTC).timestamp()
    mocked.post(
        url("api/v3/live/1/rtsp/link"),
        payload={"url": "rtsp://zm.local:8554/1?st=signed", "expires_at": expires},
    )

    first = await client.async_get_rtsp_url(1)
    second = await client.async_get_rtsp_url(1)

    assert first == second == "rtsp://zm.local:8554/1?st=signed"
    (request,) = calls(mocked, "POST", "api/v3/live/1/rtsp/link")
    assert request.kwargs["json"] == {"ttl_seconds": 7 * 24 * 3600}


async def test_rtsp_switched_off_is_not_asked_again_at_once(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    mocked.post(url(r"api/v3/live/\d+/rtsp/link"), status=503, repeat=True)

    assert await client.async_get_rtsp_url(1) is None
    assert await client.async_get_rtsp_url(2) is None
    assert len(calls(mocked, "POST", "api/v3/live/1/rtsp/link")) == 1
    assert calls(mocked, "POST", "api/v3/live/2/rtsp/link") == []


async def test_live_session_is_started_once(
    client: ZoneMinderV3Client, zm_api: aioresponses
) -> None:
    zm_api.post(url("api/v3/live/1/start"), payload={"status": "started"}, repeat=True)

    await client.async_prepare_live(1)
    await client.async_prepare_live(1)

    (start,) = calls(zm_api, "POST", "api/v3/live/1/start")
    assert start.kwargs["json"] == {"enable_hls": True, "enable_webrtc": True}


async def test_snapshot(client: ZoneMinderV3Client, mocked: aioresponses) -> None:
    register_login(mocked)
    mocked.get(url("api/v3/monitors/1/snapshot"), status=401)
    mocked.get(url("api/v3/monitors/1/snapshot"), body=b"\xff\xd8jpeg")
    assert await client.async_get_snapshot(1) == b"\xff\xd8jpeg"


async def test_snapshot_failure(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    mocked.get(url("api/v3/monitors/1/snapshot"), status=500)
    assert await client.async_get_snapshot(1) is None


async def test_snapshot_of_a_monitor_not_capturing(
    client: ZoneMinderV3Client,
    mocked: aioresponses,
    caplog: pytest.LogCaptureFixture,
) -> None:
    register_login(mocked)
    mocked.get(url("api/v3/monitors/1/snapshot"), status=404)
    assert await client.async_get_snapshot(1) is None
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


async def test_media_is_streamed_with_the_token(
    client: ZoneMinderV3Client, mocked: aioresponses
) -> None:
    register_login(mocked)
    path = client.get_event_media_path(298)
    mocked.get(url(path), body=b"mp4 bytes")

    async with client.async_stream_media(path, headers={"Range": "bytes=0-"}) as resp:
        assert await resp.read() == b"mp4 bytes"

    (request,) = calls(mocked, "GET", path)
    assert bearer(request) == "Bearer access-token"
    assert request.kwargs["headers"]["Range"] == "bytes=0-"


def test_media_paths(client: ZoneMinderV3Client) -> None:
    assert client.get_live_media_path(1) == "api/v3/live/1/hls/master.m3u8"
    assert client.get_event_media_path(5) == "api/v3/events/5/video"
    assert client.get_event_thumbnail_path(5) == "api/v3/events/5/thumbnail"
    assert client.get_webrtc_signaling_url(1) == (
        "ws://192.168.0.45:8080/api/v3/live/1/webrtc/ws"
    )
