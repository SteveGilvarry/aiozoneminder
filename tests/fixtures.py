"""Shared test data.

The payloads mirror what a real ZoneMinder 1.39 / zm-api 3.0 server returns,
with camera credentials removed.
"""

from __future__ import annotations

from typing import Any

HOST = "http://192.168.0.45:8080"

VERSION_RESPONSE = {
    "version": "1.39.22",
    "api_version": "3.0.0-alpha.1",
    "db_version": "1.39.22",
}


def monitor(
    monitor_id: int,
    name: str,
    *,
    capturing: str = "Always",
    analysing: str = "None",
    recording: str = "Always",
    orientation: str = "Rotate0",
    controllable: int = 0,
    mqtt_enabled: int = 0,
) -> dict[str, Any]:
    """Build a zm-api monitor payload."""
    return {
        "id": monitor_id,
        "name": name,
        "type": "Ffmpeg",
        "function": "Monitor",
        "capturing": capturing,
        "analysing": analysing,
        "recording": recording,
        "decoding": "Ondemand",
        "enabled": None,
        "deleted": False,
        "width": 1920,
        "height": 1080,
        "orientation": orientation,
        "importance": "Normal",
        "controllable": controllable,
        "control_id": 3 if controllable else None,
        "mqtt_enabled": mqtt_enabled,
        "storage_id": 1,
        "server_id": 0,
        "protocol": "rtsp",
        "host": "192.168.0.225",
        "path": "rtsp://admin:secret@192.168.0.225:554/Streaming/Channels/101",
        "port": "554",
        "notes": "",
    }


MONITORS = [
    monitor(1, "Driveway", recording="Always"),
    monitor(2, "Back door", analysing="Always", recording="OnMotion", mqtt_enabled=1),
    monitor(3, "Gate", controllable=1, orientation="Rotate90"),
]

MONITOR_STATUS = [
    {
        "monitor_id": 1,
        "status": "Connected",
        "capture_fps": "10.94",
        "analysis_fps": "0.00",
        "capture_bandwidth": 1474209,
        "updated_on": "2026-08-22T13:52:54+00:00",
    },
    {
        "monitor_id": 2,
        "status": "Connected",
        "capture_fps": "9.83",
        "analysis_fps": "9.80",
        "capture_bandwidth": 68649,
        "updated_on": "2026-08-22T13:52:55+00:00",
    },
    {
        "monitor_id": 3,
        "status": "NotRunning",
        "capture_fps": "0.00",
        "analysis_fps": "0.00",
        "capture_bandwidth": 0,
        "updated_on": "2026-08-22T13:52:57+00:00",
    },
]


def event(
    event_id: int,
    monitor_id: int,
    *,
    cause: str = "Continuous",
    start: str = "2026-08-22T13:44:52Z",
    end: str | None = "2026-08-22T13:54:52Z",
    alarm_frames: int = 0,
    default_video: str | None = "video.h264.mp4",
) -> dict[str, Any]:
    """Build a zm-api event payload."""
    return {
        "id": event_id,
        "monitor_id": monitor_id,
        "name": "New Event",
        "cause": cause,
        "start_date_time": start,
        "end_date_time": end,
        "length": "600.02",
        "frames": 6001,
        "alarm_frames": alarm_frames,
        "max_score": 42 if alarm_frames else 0,
        "avg_score": 10 if alarm_frames else 0,
        "tot_score": 100 if alarm_frames else 0,
        "disk_space": 174013951,
        "default_video": default_video,
        "archived": 0,
        "notes": "",
        "width": 1920,
        "height": 1080,
    }


EVENTS = [
    # Monitor 1 records continuously: a stream of events with no motion in them.
    event(300, 1, end=None, default_video="incomplete.h264.mp4"),
    event(299, 1),
    # Monitor 2 analyses, so its events are real motion.
    event(298, 2, cause="Motion", alarm_frames=17),
    event(297, 2, cause="Motion", alarm_frames=4),
]

RUN_STATES = [
    {"id": 1, "name": "default", "definition": "", "is_active": 0},
    {
        "id": 2,
        "name": "Home",
        "definition": "1:Always:None:Always,2:Always:None:None,3:Always:None:None",
        "is_active": 1,
    },
    {
        "id": 3,
        "name": "Away",
        "definition": (
            "1:Always:Always:Always,2:Always:Always:OnMotion,3:Always:Always:OnMotion"
        ),
        "is_active": 0,
    },
]

EVENT_SUMMARY = {
    "monitor_id": 1,
    "total_events": 126,
    "total_event_disk_space": 53502929568,
    "hour_events": 6,
    "hour_event_disk_space": 2974840561,
    "day_events": 85,
    "day_event_disk_space": 53168507607,
    "week_events": 86,
    "week_event_disk_space": 53168507607,
    "month_events": 86,
    "month_event_disk_space": 53168507607,
    "archived_events": 1,
    "archived_event_disk_space": 334421961,
}

SYSTEM_STATUS = {
    "running": True,
    "daemons": [
        {
            "id": "zmc -m 1",
            "name": "zmc -m 1",
            "state": "running",
            "pid": 1,
            "monitor_id": 1,
        },
        {"id": "zmstats.pl", "name": "zmstats.pl", "state": "running", "pid": 2},
        {"id": "zmwatch.pl", "name": "zmwatch.pl", "state": "stopped", "pid": 3},
    ],
    "stats": None,
}

STORAGE = [
    {
        "id": 1,
        "name": "Default",
        "path": "/var/cache/zoneminder/events",
        "type": "local",
        "scheme": "Medium",
        "server_id": 0,
        "url": None,
        "disk_space": 51762574243,
        "do_delete": 1,
        "enabled": 1,
    }
]

CONFIGS = [
    {
        "id": 1,
        "name": "ZM_MQTT_TOPIC_PREFIX",
        "value": "ZoneMinder",
        "category": "mqtt",
    },
    {"id": 2, "name": "ZM_MQTT_HOSTNAME", "value": "192.168.0.66", "category": "mqtt"},
    {"id": 3, "name": "ZM_MQTT_PASSWORD", "value": "topsecret", "category": "mqtt"},
    {
        "id": 4,
        "name": "ZM_GO2RTC_PATH",
        "value": "http://192.168.0.45:1984/api",
        "category": "system",
    },
]


def paginated(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap items the way zm-api's paginated endpoints do."""
    return {
        "items": items,
        "total": len(items),
        "per_page": 500,
        "current_page": 1,
        "last_page": 1,
    }


# A live HLS playlist with segments, as zm-api serves once a session is warm.
LIVE_PLAYLIST = (
    "#EXTM3U\n"
    "#EXT-X-VERSION:6\n"
    "#EXT-X-TARGETDURATION:5\n"
    '#EXT-X-MAP:URI="init.mp4"\n'
    "#EXTINF:5.000,\n"
    "segment_00000.m4s\n"
)
