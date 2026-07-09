#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path
from typing import Any

from bosch_ble import live, mcsp
from bosch_ble._common import format_cli_error, normalize_uuid, Services, ts, validate_address


STOP = asyncio.Event()


def collect_log_characteristics(services: Services) -> tuple[list[str], list[str]]:
    notify_chars: list[str] = []
    read_chars: list[str] = []
    for service in services:
        if normalize_uuid(service.uuid) == mcsp.MCSP_SERVICE_UUID:
            continue
        for char in service.characteristics:
            props = set(char.properties)
            if "notify" in props or "indicate" in props:
                notify_chars.append(normalize_uuid(char.uuid))
            if "read" in props:
                read_chars.append(normalize_uuid(char.uuid))
    return notify_chars, read_chars


async def main(address: str, out_file: str | None = None) -> None:
    global STOP
    STOP = asyncio.Event()
    path = Path(out_file or f"ble_log-{ts()}.txt")
    print(f"Connecting to {address} ...", flush=True)
    print(f"Logging to {path}", flush=True)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, STOP.set)
        except NotImplementedError:
            pass

    async with live.connected_client(address, timeout=20.0) as client:
        print(f"Connected: {client.is_connected}", flush=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"{ts()} CONNECTED {address}\n")

            def notify_handler(sender: Any, data: bytearray) -> None:
                line = f"{ts()} NOTIFY sender={sender} hex={bytes(data).hex()} raw={bytes(data)!r}\n"
                print(line, end="", flush=True)
                fh.write(line)
                fh.flush()

            notify_chars: list[str] = []
            read_chars: list[str] = []

            notify_chars, read_chars = collect_log_characteristics(client.services)

            print("Subscribing to notifiable characteristics...", flush=True)
            for uuid in notify_chars:
                try:
                    await client.start_notify(uuid, notify_handler)
                    line = f"{ts()} SUBSCRIBED {uuid}\n"
                except Exception as exc:
                    line = f"{ts()} SUBSCRIBE_FAILED {uuid} error={exc}\n"
                print(line, end="", flush=True)
                fh.write(line)

            fh.flush()

            print("Polling readable characteristics every 10 seconds. Ctrl-C to stop.", flush=True)
            while not STOP.is_set():
                for uuid in read_chars:
                    try:
                        data = await client.read_gatt_char(uuid)
                        line = f"{ts()} READ uuid={uuid} hex={bytes(data).hex()} raw={bytes(data)!r}\n"
                    except Exception as exc:
                        line = f"{ts()} READ_FAILED uuid={uuid} error={exc}\n"
                    print(line, end="", flush=True)
                    fh.write(line)

                fh.flush()
                await asyncio.sleep(10)

            print("Stopping notifications...", flush=True)
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

    address = validate_address(sys.argv[1])
    output = sys.argv[2] if len(sys.argv) == 3 else f"ble_log-{ts()}.txt"
    try:
        asyncio.run(main(address, output))
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {format_cli_error(exc)}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
