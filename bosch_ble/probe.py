#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path
from typing import Any

from bleak import BleakClient

from bosch_ble import live
from bosch_ble._common import (
    BleakCharacteristic,
    format_cli_error,
    normalize_uuid,
    Services,
    ts,
    validate_address,
)


PROBE_TARGET_UUIDS = (
    "00000012-eaa2-11e9-81b4-2a2ae2dbcce4",
    "00000021-eaa2-11e9-81b4-2a2ae2dbcce4",
    "00000042-eaa2-11e9-81b4-2a2ae2dbcce4",
    "0000eba2-eaa2-11e9-81b4-2a2ae2dbcce4",
    "0000ebd1-eaa2-11e9-81b4-2a2ae2dbcce4",
)
PROBE_PAYLOADS = (
    b"\x00",
    b"\x00\x00",
    b"\x01",
    b"\x01\x00",
)
PROBE_DELAY_SECONDS = 1.0
STOP = asyncio.Event()


def is_bosch_uuid(value: object) -> bool:
    return normalize_uuid(value).endswith("-eaa2-11e9-81b4-2a2ae2dbcce4")


def probe_write_response(char: BleakCharacteristic) -> bool:
    properties = set(char.properties)
    return "write" in properties and "write-without-response" not in properties


def collect_probe_chars(
    services: Services,
) -> tuple[list[BleakCharacteristic], list[BleakCharacteristic], list[BleakCharacteristic]]:
    notify_chars: list[BleakCharacteristic] = []
    read_chars: list[BleakCharacteristic] = []
    write_chars: list[BleakCharacteristic] = []
    target_uuids = {normalize_uuid(uuid) for uuid in PROBE_TARGET_UUIDS}

    for service in services:
        for char in service.characteristics:
            uuid = normalize_uuid(char.uuid)
            props = set(char.properties)
            if is_bosch_uuid(uuid) and ("notify" in props or "indicate" in props):
                notify_chars.append(char)
            if "read" in props:
                read_chars.append(char)
            if uuid in target_uuids and ("write" in props or "write-without-response" in props):
                write_chars.append(char)

    return notify_chars, read_chars, write_chars


async def snapshot_reads(
    client: BleakClient,
    read_chars: list[BleakCharacteristic],
    emit,
    label: str,
) -> dict[str, bytes]:
    values: dict[str, bytes] = {}
    for char in read_chars:
        uuid = normalize_uuid(char.uuid)
        try:
            data = bytes(await client.read_gatt_char(uuid))
            values[uuid] = data
            emit(f"{ts()} {label} uuid={uuid} hex={data.hex()} raw={data!r}")
        except Exception as exc:
            emit(f"{ts()} {label}_FAILED uuid={uuid} error={exc}")
    return values


async def main(
    address: str,
    out_file: str | None = None,
    *,
    backend: live.Backend = "bluez",
    esphome_host: str | None = None,
) -> None:
    global STOP
    STOP = asyncio.Event()
    path = Path(out_file or f"ble_probe-{ts()}.txt")
    print(f"Connecting to {address} via {backend} ...", flush=True)
    print(f"Probing to {path}", flush=True)

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
            def emit(line: str) -> None:
                print(line, flush=True)
                fh.write(f"{line}\n")
                fh.flush()

            emit(f"{ts()} CONNECTED {address}")

            def notify_handler(sender: Any, data: bytearray) -> None:
                emit(
                    f"{ts()} NOTIFY sender={sender} hex={bytes(data).hex()} raw={bytes(data)!r}"
                )

            notify_chars, read_chars, write_chars = collect_probe_chars(client.services)
            if not write_chars:
                raise RuntimeError("No Bosch probe characteristics were found.")

            emit("Subscribing to notifiable characteristics...")
            for char in notify_chars:
                uuid = normalize_uuid(getattr(char, "uuid", ""))
                try:
                    await client.start_notify(uuid, notify_handler)
                    emit(f"{ts()} SUBSCRIBED {uuid}")
                except Exception as exc:
                    emit(f"{ts()} SUBSCRIBE_FAILED {uuid} error={exc}")

            baseline = await snapshot_reads(client, read_chars, emit, "BASELINE")

            for char in write_chars:
                if STOP.is_set():
                    break
                uuid = normalize_uuid(getattr(char, "uuid", ""))
                response = probe_write_response(char)
                for payload in PROBE_PAYLOADS:
                    if STOP.is_set():
                        break
                    emit(f"{ts()} PROBE uuid={uuid} payload={payload.hex()}")
                    try:
                        await client.write_gatt_char(uuid, payload, response=response)
                        emit(f"{ts()} PROBE_WRITE_OK uuid={uuid} payload={payload.hex()}")
                    except Exception as exc:
                        emit(f"{ts()} PROBE_WRITE_FAILED uuid={uuid} payload={payload.hex()} error={exc}")
                        continue

                    await asyncio.sleep(PROBE_DELAY_SECONDS)
                    current = await snapshot_reads(client, read_chars, emit, "READ")
                    for read_uuid, current_value in current.items():
                        previous_value = baseline.get(read_uuid)
                        if previous_value != current_value:
                            before = previous_value.hex() if previous_value is not None else ""
                            emit(
                                f"{ts()} READ_CHANGE uuid={read_uuid} before={before} after={current_value.hex()}"
                            )
                    baseline = current

            emit("Stopping notifications...")
            for char in notify_chars:
                uuid = normalize_uuid(getattr(char, "uuid", ""))
                try:
                    await client.stop_notify(uuid)
                    emit(f"{ts()} UNSUBSCRIBED {uuid}")
                except Exception as exc:
                    emit(f"{ts()} UNSUBSCRIBE_FAILED {uuid} error={exc}")


def cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Probe BLE characteristics on a Bosch eBike"
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
