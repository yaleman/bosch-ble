#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from bleak import BleakClient

from bosch_ble import dump_gatt


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


def ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def format_cli_error(exc: Exception) -> str:
    return str(exc) or type(exc).__name__


def normalize_uuid(value: object) -> str:
    return str(value).lower()


def is_bosch_uuid(value: object) -> bool:
    return normalize_uuid(value).endswith("-eaa2-11e9-81b4-2a2ae2dbcce4")


def probe_write_response(char: object) -> bool:
    properties = set(getattr(char, "properties", []))
    return "write" in properties and "write-without-response" not in properties


def collect_probe_chars(services: object) -> tuple[list[object], list[object], list[object]]:
    notify_chars: list[object] = []
    read_chars: list[object] = []
    write_chars: list[object] = []
    target_uuids = {normalize_uuid(uuid) for uuid in PROBE_TARGET_UUIDS}

    for service in services:
        for char in getattr(service, "characteristics", []):
            uuid = normalize_uuid(getattr(char, "uuid", ""))
            props = set(getattr(char, "properties", []))
            if is_bosch_uuid(uuid) and ("notify" in props or "indicate" in props):
                notify_chars.append(char)
            if "read" in props:
                read_chars.append(char)
            if uuid in target_uuids and ("write" in props or "write-without-response" in props):
                write_chars.append(char)

    return notify_chars, read_chars, write_chars


async def snapshot_reads(
    client: BleakClient,
    read_chars: list[object],
    emit,
    label: str,
) -> dict[str, bytes]:
    values: dict[str, bytes] = {}
    for char in read_chars:
        uuid = normalize_uuid(getattr(char, "uuid", ""))
        try:
            data = bytes(await client.read_gatt_char(uuid))
            values[uuid] = data
            emit(f"{ts()} {label} uuid={uuid} hex={data.hex()} raw={data!r}")
        except Exception as exc:
            emit(f"{ts()} {label}_FAILED uuid={uuid} error={exc}")
    return values


async def main(address: str, out_file: str = "ble_probe.txt") -> None:
    global STOP
    STOP = asyncio.Event()
    path = Path(out_file)
    print(f"Connecting to {address} ...", flush=True)
    print(f"Probing to {path}", flush=True)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, STOP.set)
        except NotImplementedError:
            pass

    state = await dump_gatt.prepare_connection(address)
    target = dump_gatt.client_target_for_state(state)

    async with BleakClient(target, timeout=20.0) as client:
        print(f"Connected: {client.is_connected}", flush=True)
        if not client.is_connected:
            raise RuntimeError("Failed to connect")

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
    if len(sys.argv) not in {2, 3}:
        print(f"Usage: {sys.argv[0]} <BLE_ADDRESS> [output_file]")
        raise SystemExit(2)

    address = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) == 3 else "ble_probe.txt"
    try:
        asyncio.run(main(address, output))
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {format_cli_error(exc)}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
