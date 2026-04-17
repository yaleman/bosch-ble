#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from bleak import BleakClient


STOP = asyncio.Event()


def ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


async def main(address: str, out_file: str = "ble_log.txt") -> None:
    path = Path(out_file)
    print(f"Connecting to {address} ...")
    print(f"Logging to {path.resolve()}")

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, STOP.set)
        except NotImplementedError:
            pass

    async with BleakClient(address, timeout=20.0) as client:
        print(f"Connected: {client.is_connected}")
        if not client.is_connected:
            raise RuntimeError("Failed to connect")

        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"{ts()} CONNECTED {address}\n")

            def notify_handler(sender: Any, data: bytearray) -> None:
                line = f"{ts()} NOTIFY sender={sender} hex={bytes(data).hex()} raw={bytes(data)!r}\n"
                print(line, end="")
                fh.write(line)
                fh.flush()

            notify_chars: list[str] = []
            read_chars: list[str] = []

            for service in client.services:
                for char in service.characteristics:
                    props = set(char.properties)
                    if "notify" in props or "indicate" in props:
                        notify_chars.append(char.uuid)
                    if "read" in props:
                        read_chars.append(char.uuid)

            print("Subscribing to notifiable characteristics...")
            for uuid in notify_chars:
                try:
                    await client.start_notify(uuid, notify_handler)
                    line = f"{ts()} SUBSCRIBED {uuid}\n"
                except Exception as exc:
                    line = f"{ts()} SUBSCRIBE_FAILED {uuid} error={exc}\n"
                print(line, end="")
                fh.write(line)

            fh.flush()

            print("Polling readable characteristics every 10 seconds. Ctrl-C to stop.")
            while not STOP.is_set():
                for uuid in read_chars:
                    try:
                        data = await client.read_gatt_char(uuid)
                        line = f"{ts()} READ uuid={uuid} hex={bytes(data).hex()} raw={bytes(data)!r}\n"
                    except Exception as exc:
                        line = f"{ts()} READ_FAILED uuid={uuid} error={exc}\n"
                    print(line, end="")
                    fh.write(line)

                fh.flush()
                await asyncio.sleep(10)

            print("Stopping notifications...")
            for uuid in notify_chars:
                try:
                    await client.stop_notify(uuid)
                    fh.write(f"{ts()} UNSUBSCRIBED {uuid}\n")
                except Exception as exc:
                    fh.write(f"{ts()} UNSUBSCRIBE_FAILED {uuid} error={exc}\n")


def cli() -> None:
    if len(sys.argv) not in {2, 3}:
        print(f"Usage: {sys.argv[0]} <BLE_ADDRESS> [output_file]")
        raise SystemExit(2)

    address = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) == 3 else "ble_log.txt"
    asyncio.run(main(address, output))


if __name__ == "__main__":
    cli()
