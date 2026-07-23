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


async def main(
    address: str,
    out_file: str | None = None,
    *,
    backend: live.Backend = "bluez",
    esphome_host: str | None = None,
) -> None:
    global STOP
    STOP = asyncio.Event()
    path = Path(out_file or f"ble_log-{ts()}.txt")
    print(f"Connecting to {address} via {backend} ...", flush=True)
    print(f"Logging to {path}", flush=True)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, STOP.set)
        except NotImplementedError:
            pass

    async with live.connected_client(
        address, timeout=20.0, backend=backend, esphome_host=esphome_host
    ) as client:
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
    import argparse

    parser = argparse.ArgumentParser(
        description="Log BLE characteristic values from a Bosch eBike"
    )
    parser.add_argument("address", help="BLE address of the bike (XX:XX:XX:XX:XX:XX)")
    parser.add_argument("output_file", nargs="?", help="Output file path")
    parser.add_argument(
        "--backend",
        choices=["bluez", "esphome"],
        default="bluez",
        help="Connection backend (default: bluez)",
    )
    parser.add_argument(
        "--esphome-host",
        help="ESPHome proxy host address (required for esphome backend)",
    )

    args = parser.parse_args()
    address = validate_address(args.address)

    if args.backend == "esphome" and not args.esphome_host:
        parser.error("--esphome-host is required when using --backend esphome")

    try:
        asyncio.run(
            main(
                address,
                args.output_file,
                backend=args.backend,
                esphome_host=args.esphome_host,
            )
        )
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {format_cli_error(exc)}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
