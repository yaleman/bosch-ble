from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from bosch_ble.scan import (
    ScannerApp,
    SeenDevice,
    SortMode,
    build_detail_lines,
    build_column_labels,
    build_table_rows,
    clear_terminal,
    cli,
    format_age,
    load_ignored_addresses,
    save_ignored_addresses,
    toggle_visible_ignored,
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


def test_build_table_rows_can_sort_by_address() -> None:
    now = datetime.now()
    devices = {
        "CC:CC": make_device(name="zeta", seconds_ago=5),
        "AA:AA": make_device(name="beta", seconds_ago=4),
        "BB:BB": make_device(name="alpha", seconds_ago=3),
    }

    rows = build_table_rows(devices, now=now, sort_mode=SortMode.ADDRESS)

    assert [row.address for row in rows] == ["AA:AA", "BB:BB", "CC:CC"]


def test_build_table_rows_marks_ignored_devices() -> None:
    now = datetime.now()
    devices = {
        "AA:AA": make_device(name="ignored", seconds_ago=1),
        "BB:BB": make_device(name="active", seconds_ago=2),
    }

    rows = build_table_rows(
        devices,
        now=now,
        sort_mode=SortMode.RECENT,
        ignored_addresses={"AA:AA"},
    )

    assert rows[0].ignored is True
    assert rows[1].ignored is False


def test_build_table_rows_can_hide_ignored_devices() -> None:
    now = datetime.now()
    devices = {
        "AA:AA": make_device(name="ignored", seconds_ago=1),
        "BB:BB": make_device(name="active", seconds_ago=2),
    }

    rows = build_table_rows(
        devices,
        now=now,
        sort_mode=SortMode.RECENT,
        ignored_addresses={"AA:AA"},
        hide_ignored=True,
    )

    assert [row.address for row in rows] == ["BB:BB"]


def test_build_column_labels_marks_active_sort_column_red() -> None:
    labels = build_column_labels(SortMode.ADDRESS)

    assert labels[0].plain == "Name"
    assert labels[0].style == "none"
    assert labels[1].plain == "Address"
    assert labels[1].style == "red"


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


def test_ignore_store_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "ignored.json"

    save_ignored_addresses(path, {"aa:aa", "CC:CC"})

    assert json.loads(path.read_text()) == ["AA:AA", "CC:CC"]
    assert load_ignored_addresses(path) == {"AA:AA", "CC:CC"}


def test_toggle_visible_ignored_adds_or_removes_all_visible() -> None:
    visible = ["AA:AA", "BB:BB"]

    ignored = toggle_visible_ignored({"AA:AA"}, visible)
    assert ignored == {"AA:AA", "BB:BB"}

    ignored = toggle_visible_ignored({"AA:AA", "BB:BB", "CC:CC"}, visible)
    assert ignored == {"CC:CC"}


class FakeScanner:
    def __init__(self, detection_callback=None) -> None:
        self.detection_callback = detection_callback

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


def test_sort_binding_cycles_through_address_mode() -> None:
    async def run() -> None:
        with patch("bosch_ble.scan.BleakScanner", FakeScanner):
            app = ScannerApp()
            async with app.run_test() as pilot:
                assert app.sort_mode is SortMode.RECENT
                await pilot.press("s")
                await pilot.pause()
                assert app.sort_mode is SortMode.RSSI
                await pilot.press("s")
                await pilot.pause()
                assert app.sort_mode is SortMode.NAME
                await pilot.press("s")
                await pilot.pause()
                assert app.sort_mode is SortMode.ADDRESS
                app.exit()

    asyncio.run(run())


def test_enter_on_selected_row_exits_with_address(tmp_path: Path) -> None:
    ignore_path = tmp_path / "ignored.json"

    async def run() -> None:
        with patch("bosch_ble.scan.BleakScanner", FakeScanner):
            from bosch_ble import scan

            with scan.DEVICES_LOCK:
                scan.DEVICES.clear()
                scan.DEVICES.update(
                    {
                        "AA:AA": make_device(name="one", seconds_ago=1),
                        "BB:BB": make_device(name="two", seconds_ago=2),
                    }
                )

            app = ScannerApp(ignore_store_path=ignore_path)
            async with app.run_test() as pilot:
                await pilot.pause()
                assert app.selected_address == "AA:AA"
                await pilot.press("enter")
                await pilot.pause()

            assert app.return_value == "AA:AA"

            with scan.DEVICES_LOCK:
                scan.DEVICES.clear()

    asyncio.run(run())


def test_ignore_bindings_update_visible_devices_and_persist(tmp_path: Path) -> None:
    ignore_path = tmp_path / "ignored.json"

    async def run() -> None:
        with patch("bosch_ble.scan.BleakScanner", FakeScanner):
            from bosch_ble import scan

            with scan.DEVICES_LOCK:
                scan.DEVICES.clear()
                scan.DEVICES.update(
                    {
                        "AA:AA": make_device(name="one", seconds_ago=1),
                        "BB:BB": make_device(name="two", seconds_ago=2),
                    }
                )

            app = ScannerApp(ignore_store_path=ignore_path)
            async with app.run_test() as pilot:
                await pilot.pause()
                assert app.selected_address == "AA:AA"

                await pilot.press("i")
                await pilot.pause()
                assert app.ignored_addresses == {"AA:AA"}
                assert load_ignored_addresses(ignore_path) == {"AA:AA"}

                await pilot.press("I")
                await pilot.pause()
                assert app.ignored_addresses == {"AA:AA", "BB:BB"}
                assert load_ignored_addresses(ignore_path) == {"AA:AA", "BB:BB"}

                await pilot.press("I")
                await pilot.pause()
                assert app.ignored_addresses == set()
                assert load_ignored_addresses(ignore_path) == set()
                app.exit()

            with scan.DEVICES_LOCK:
                scan.DEVICES.clear()

    asyncio.run(run())


def test_hide_ignored_binding_filters_visible_rows(tmp_path: Path) -> None:
    ignore_path = tmp_path / "ignored.json"

    async def run() -> None:
        with patch("bosch_ble.scan.BleakScanner", FakeScanner):
            from bosch_ble import scan

            with scan.DEVICES_LOCK:
                scan.DEVICES.clear()
                scan.DEVICES.update(
                    {
                        "AA:AA": make_device(name="one", seconds_ago=1),
                        "BB:BB": make_device(name="two", seconds_ago=2),
                    }
                )

            save_ignored_addresses(ignore_path, {"AA:AA"})
            app = ScannerApp(ignore_store_path=ignore_path)
            async with app.run_test() as pilot:
                await pilot.pause()
                assert app.hide_ignored is False
                assert app.visible_addresses == ["AA:AA", "BB:BB"]

                await pilot.press("h")
                await pilot.pause()
                assert app.hide_ignored is True
                assert app.visible_addresses == ["BB:BB"]

                await pilot.press("h")
                await pilot.pause()
                assert app.hide_ignored is False
                assert app.visible_addresses == ["AA:AA", "BB:BB"]
                app.exit()

            with scan.DEVICES_LOCK:
                scan.DEVICES.clear()

    asyncio.run(run())


def test_clear_terminal_writes_ansi_clear_sequence(capsys) -> None:
    clear_terminal()

    assert capsys.readouterr().out == "\033[2J\033[H"


def test_cli_clears_terminal_after_app_exit() -> None:
    events: list[str] = []

    class FakeApp:
        def run(self) -> None:
            events.append("run")

    with patch("bosch_ble.scan.ScannerApp", return_value=FakeApp()):
        with patch("bosch_ble.scan.clear_terminal", side_effect=lambda: events.append("clear")):
            cli()

    assert events == ["run", "clear"]


def test_cli_execs_dump_gatt_for_selected_address() -> None:
    events: list[object] = []

    class FakeApp:
        def run(self) -> str:
            events.append("run")
            return "AA:BB"

    with patch("bosch_ble.scan.ScannerApp", return_value=FakeApp()):
        with patch("bosch_ble.scan.clear_terminal", side_effect=lambda: events.append("clear")):
            with patch(
                "bosch_ble.scan.os.execvp",
                side_effect=lambda cmd, argv: events.append(("exec", cmd, argv)),
            ):
                cli()

    assert events == [
        "run",
        "clear",
        ("exec", "bosch-ble-dump-gatt", ["bosch-ble-dump-gatt", "AA:BB"]),
    ]
