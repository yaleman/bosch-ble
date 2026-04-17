from __future__ import annotations

from datetime import datetime, timedelta

from bosch_ble.scan import (
    SeenDevice,
    SortMode,
    build_detail_lines,
    build_table_rows,
    format_age,
)


def make_device(
    *,
    name: str | None = None,
    seconds_ago: float = 0.0,
    count: int = 1,
    rssi: int | None = None,
    uuids: list[str] | None = None,
    manufacturer_data: dict[int, bytes] | None = None,
    service_data: dict[str, bytes] | None = None,
) -> SeenDevice:
    now = datetime.now()
    seen_at = now - timedelta(seconds=seconds_ago)
    return SeenDevice(
        name=name,
        first_seen=seen_at,
        last_seen=seen_at,
        count=count,
        rssi=rssi,
        uuids=uuids or [],
        manufacturer_data=manufacturer_data or {},
        service_data=service_data or {},
    )


def test_format_age_shows_compact_units() -> None:
    assert format_age(0.4) == "0.4s"
    assert format_age(61.0) == "1m01s"
    assert format_age(3661.0) == "1h01m"


def test_build_table_rows_sorts_by_recent_activity() -> None:
    now = datetime.now()
    devices = {
        "AA:AA": make_device(name="older", seconds_ago=5, count=2, rssi=-80),
        "BB:BB": make_device(name="newer", seconds_ago=1, count=4, rssi=-40),
    }

    rows = build_table_rows(devices, now=now, sort_mode=SortMode.RECENT)

    assert [row.address for row in rows] == ["BB:BB", "AA:AA"]
    assert rows[0].name == "newer"
    assert rows[0].seen == "4"


def test_build_table_rows_filters_stale_devices() -> None:
    now = datetime.now()
    devices = {
        "AA:AA": make_device(name="fresh", seconds_ago=2),
        "BB:BB": make_device(name="stale", seconds_ago=40),
    }

    rows = build_table_rows(
        devices,
        now=now,
        sort_mode=SortMode.RECENT,
        hide_stale=True,
        stale_after_seconds=30.0,
    )

    assert [row.address for row in rows] == ["AA:AA"]


def test_build_table_rows_uses_placeholder_for_missing_name_and_rssi() -> None:
    now = datetime.now()
    devices = {
        "AA:AA": make_device(name=None, seconds_ago=2, rssi=None),
    }

    rows = build_table_rows(devices, now=now, sort_mode=SortMode.RECENT)

    assert rows[0].name == "-"
    assert rows[0].rssi == "-"


def test_build_detail_lines_includes_all_advertisement_sections() -> None:
    device = make_device(
        name="sensor",
        seconds_ago=3,
        count=5,
        rssi=-55,
        uuids=["1234", "5678"],
        manufacturer_data={0x004C: bytes.fromhex("01020304")},
        service_data={"feed": bytes.fromhex("0A0B0C")},
    )

    lines = build_detail_lines("AA:BB", device, now=datetime.now())

    assert "Name: sensor" in lines
    assert "Address: AA:BB" in lines
    assert "UUIDs:" in lines
    assert "1234" in lines
    assert "Manufacturer Data:" in lines
    assert "0x004c=01020304" in lines
    assert "Service Data:" in lines
    assert "feed=0a0b0c" in lines


def test_build_detail_lines_returns_empty_state_message() -> None:
    assert build_detail_lines(None, None, now=datetime.now()) == [
        "No devices seen yet."
    ]
