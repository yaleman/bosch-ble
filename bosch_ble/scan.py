#!/usr/bin/env python3
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from threading import Lock
from typing import Any

from bleak import BleakScanner
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import DataTable, Static


@dataclass
class SeenDevice:
    name: str | None = None
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    count: int = 0
    rssi: int | None = None
    uuids: list[str] = field(default_factory=list)
    manufacturer_data: dict[int, bytes] = field(default_factory=dict)
    service_data: dict[str, bytes] = field(default_factory=dict)


@dataclass(frozen=True)
class TableRow:
    name: str
    address: str
    rssi: str
    seen: str
    age: str
    age_seconds: float
    sort_name: str
    sort_address: str
    sort_rssi: int | None


class SortMode(StrEnum):
    RECENT = "recent"
    RSSI = "rssi"
    NAME = "name"
    ADDRESS = "address"

    @property
    def label(self) -> str:
        return {
            SortMode.RECENT: "recent",
            SortMode.RSSI: "rssi",
            SortMode.NAME: "name",
            SortMode.ADDRESS: "address",
        }[self]

    def next(self) -> SortMode:
        modes = list(type(self))
        return modes[(modes.index(self) + 1) % len(modes)]


DEVICES: dict[str, SeenDevice] = {}
DEVICES_LOCK = Lock()
STALE_AFTER_SECONDS = 30.0


def fmt_bytes(data: bytes, limit: int = 32) -> str:
    hexed = data.hex()
    if len(hexed) > limit * 2:
        return hexed[: limit * 2] + "..."
    return hexed


def format_age(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"

    total_seconds = int(seconds)
    minutes, secs = divmod(total_seconds, 60)
    if total_seconds < 3600:
        return f"{minutes}m{secs:02d}s"

    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def build_table_rows(
    devices: dict[str, SeenDevice],
    *,
    now: datetime,
    sort_mode: SortMode,
    hide_stale: bool = False,
    stale_after_seconds: float = STALE_AFTER_SECONDS,
) -> list[TableRow]:
    rows: list[TableRow] = []

    for address, device in devices.items():
        age_seconds = max((now - device.last_seen).total_seconds(), 0.0)
        if hide_stale and age_seconds > stale_after_seconds:
            continue

        rows.append(
            TableRow(
                name=device.name or "-",
                address=address,
                rssi="-" if device.rssi is None else str(device.rssi),
                seen=str(device.count),
                age=format_age(age_seconds),
                age_seconds=age_seconds,
                sort_name=(device.name or "").casefold(),
                sort_address=address.casefold(),
                sort_rssi=device.rssi,
            )
        )

    if sort_mode is SortMode.RECENT:
        rows.sort(key=lambda row: (row.age_seconds, row.sort_name, row.address))
    elif sort_mode is SortMode.RSSI:
        rows.sort(
            key=lambda row: (
                row.sort_rssi is None,
                -(row.sort_rssi if row.sort_rssi is not None else -10_000),
                row.age_seconds,
                row.sort_name,
                row.address,
            )
        )
    elif sort_mode is SortMode.NAME:
        rows.sort(
            key=lambda row: (
                row.name == "-",
                row.sort_name,
                row.age_seconds,
                row.sort_address,
            )
        )
    else:
        rows.sort(
            key=lambda row: (
                row.sort_address,
                row.age_seconds,
                row.sort_name,
            )
        )

    return rows


def build_detail_lines(
    address: str | None,
    device: SeenDevice | None,
    *,
    now: datetime,
) -> list[str]:
    if address is None or device is None:
        return ["No devices seen yet."]

    lines = [
        f"Name: {device.name or '-'}",
        f"Address: {address}",
        f"RSSI: {device.rssi if device.rssi is not None else '-'}",
        f"Seen: {device.count}",
        f"Age: {format_age(max((now - device.last_seen).total_seconds(), 0.0))}",
        "",
        "UUIDs:",
    ]
    if device.uuids:
        lines.extend(device.uuids)
    else:
        lines.append("-")

    lines.extend(["", "Manufacturer Data:"])
    if device.manufacturer_data:
        lines.extend(
            f"{key:#06x}={fmt_bytes(value)}"
            for key, value in sorted(device.manufacturer_data.items())
        )
    else:
        lines.append("-")

    lines.extend(["", "Service Data:"])
    if device.service_data:
        lines.extend(
            f"{key}={fmt_bytes(value)}"
            for key, value in sorted(device.service_data.items())
        )
    else:
        lines.append("-")

    return lines


def detection_callback(device: Any, advertisement_data: Any) -> None:
    address = getattr(device, "address", "unknown")
    with DEVICES_LOCK:
        entry = DEVICES.setdefault(address, SeenDevice())
        entry.name = (
            getattr(device, "name", None) or advertisement_data.local_name or entry.name
        )
        entry.last_seen = datetime.now()
        entry.count += 1
        entry.rssi = advertisement_data.rssi
        entry.uuids = sorted(advertisement_data.service_uuids or [])
        entry.manufacturer_data = dict(advertisement_data.manufacturer_data or {})
        entry.service_data = dict(advertisement_data.service_data or {})


class ScannerApp(App[None]):
    REFRESH_INTERVAL_SECONDS = 1.0

    CSS = """
    Screen {
        layout: vertical;
    }

    #body {
        height: 1fr;
    }

    #devices {
        width: 3fr;
    }

    #details {
        width: 2fr;
        padding: 0 1;
        overflow-y: auto;
        border-left: solid $panel;
    }

    #status {
        height: 1;
        padding: 0 1;
        background: $surface;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("s", "cycle_sort", "Sort", priority=True),
        Binding("f", "toggle_stale", "Stale", priority=True),
        Binding("ctrl+c", "quit", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.sort_mode = SortMode.RECENT
        self.hide_stale = False
        self.selected_address: str | None = None
        self.scanner: BleakScanner | None = None

    def compose(self) -> ComposeResult:
        yield Horizontal(
            DataTable(id="devices"),
            Static("No devices seen yet.", id="details"),
            id="body",
        )
        yield Static("", id="status")

    async def on_mount(self) -> None:
        table = self.query_one("#devices", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("Name", "Address", "RSSI", "Seen", "Age")
        table.focus()

        self.set_interval(self.REFRESH_INTERVAL_SECONDS, self.refresh_view)
        self.scanner = BleakScanner(detection_callback=detection_callback)
        await self.scanner.start()
        self.refresh_view()

    async def on_unmount(self) -> None:
        if self.scanner is not None:
            await self.scanner.stop()

    def action_cycle_sort(self) -> None:
        self.sort_mode = self.sort_mode.next()
        self.refresh_view()

    def action_toggle_stale(self) -> None:
        self.hide_stale = not self.hide_stale
        self.refresh_view()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.selected_address = str(event.row_key.value)
        self.refresh_details()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.selected_address = str(event.row_key.value)
        self.refresh_details()

    def refresh_view(self) -> None:
        now = datetime.now()
        with DEVICES_LOCK:
            devices = deepcopy(DEVICES)

        rows = build_table_rows(
            devices,
            now=now,
            sort_mode=self.sort_mode,
            hide_stale=self.hide_stale,
        )
        table = self.query_one("#devices", DataTable)
        table.clear(columns=False)
        for row in rows:
            table.add_row(row.name, row.address, row.rssi, row.seen, row.age, key=row.address)

        visible_addresses = [row.address for row in rows]
        if not visible_addresses:
            self.selected_address = None
        elif self.selected_address not in visible_addresses:
            self.selected_address = visible_addresses[0]

        if self.selected_address is not None:
            table.move_cursor(
                row=visible_addresses.index(self.selected_address),
                column=0,
                animate=False,
                scroll=False,
            )

        self.refresh_details(devices=devices, now=now)
        self.refresh_status(device_count=len(rows))

    def refresh_details(
        self,
        *,
        devices: dict[str, SeenDevice] | None = None,
        now: datetime | None = None,
    ) -> None:
        if devices is None:
            with DEVICES_LOCK:
                devices = deepcopy(DEVICES)
        if now is None:
            now = datetime.now()

        detail_widget = self.query_one("#details", Static)
        device = None if self.selected_address is None else devices.get(self.selected_address)
        detail_widget.update("\n".join(build_detail_lines(self.selected_address, device, now=now)))

    def refresh_status(self, *, device_count: int) -> None:
        status = self.query_one("#status", Static)
        stale_state = "hidden" if self.hide_stale else "shown"
        status.update(
            f"Devices:{device_count}  Sort:{self.sort_mode.label}  "
            f"Stale:{stale_state}  ↑↓ select  s sort  f stale  q quit"
        )


def cli() -> None:
    ScannerApp().run()


if __name__ == "__main__":
    cli()
