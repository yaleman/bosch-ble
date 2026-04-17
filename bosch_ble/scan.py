#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import signal
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from bleak import BleakScanner


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


DEVICES: dict[str, SeenDevice] = {}
STOP = asyncio.Event()


def fmt_bytes(data: bytes, limit: int = 32) -> str:
    hexed = data.hex()
    if len(hexed) > limit * 2:
        return hexed[: limit * 2] + "..."
    return hexed


def detection_callback(device: Any, advertisement_data: Any) -> None:
    address = getattr(device, "address", "unknown")
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


async def printer() -> None:
    while not STOP.is_set():
        print("\033[2J\033[H", end="")  # clear screen
        print(f"BLE scan snapshot at {datetime.now().isoformat(timespec='seconds')}")
        print("=" * 100)
        if not DEVICES:
            print("No devices seen yet.")
        else:
            for address, dev in sorted(
                DEVICES.items(),
                key=lambda item: (
                    item[1].name or "",
                    item[1].last_seen,
                ),
                reverse=True,
            ):
                age = (datetime.now() - dev.last_seen).total_seconds()
                print(f"Address: {address}")
                print(f"Name:    {dev.name}")
                print(f"RSSI:    {dev.rssi}")
                print(f"Seen:    {dev.count} times, last {age:.1f}s ago")
                if dev.uuids:
                    print(f"UUIDs:   {', '.join(dev.uuids)}")
                if dev.manufacturer_data:
                    print(
                        "Mfg:     "
                        + ", ".join(
                            f"{k:#06x}={fmt_bytes(v)}"
                            for k, v in dev.manufacturer_data.items()
                        )
                    )
                if dev.service_data:
                    print(
                        "SvcData: "
                        + ", ".join(
                            f"{k}={fmt_bytes(v)}" for k, v in dev.service_data.items()
                        )
                    )
                print("-" * 100)
        await asyncio.sleep(2)


async def main() -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, STOP.set)
        except NotImplementedError:
            pass

    scanner = BleakScanner(detection_callback=detection_callback)
    await scanner.start()
    try:
        await printer()
    finally:
        await scanner.stop()


def cli() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    cli()
