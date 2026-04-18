#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import sys

from bleak import BleakClient
from bleak.backends.characteristic import CharacteristicPropertyName

from bosch_ble import bluez

DISCOVERY_RETRY_ATTEMPTS = 3
REDISCOVERY_TIMEOUT = 10.0


def props_to_str(props: list[str | "CharacteristicPropertyName"]) -> str:
    return ",".join(sorted(props))


def format_cli_error(exc: Exception) -> str:
    return str(exc) or type(exc).__name__


def retry_message(error: Exception, address: str) -> str | None:
    message = str(error).lower()
    if "failed to discover services" in message:
        return f"Retrying service discovery for {address} ..."
    if "operation already in progress" in message:
        return f"Retrying connection setup for {address} ..."
    return None


async def resolve_device(address: str) -> bluez.BluezState:
    state = await bluez.preflight_device(address)
    bluez.print_preflight_summary(state)

    if state.device is None:
        print(f"Rediscovering {address} ...")
        state = await bluez.preflight_device(address, scan_timeout=REDISCOVERY_TIMEOUT)
        bluez.print_preflight_summary(state)

    return state


async def prepare_connection(address: str) -> bluez.BluezState:
    state = await resolve_device(address)
    connected_state = bluez.assist_connection(address)
    if bluez.busctl_available() and connected_state.services_resolved is not True:
        print(f"Waiting for BlueZ services for {address} ...")
        connected_state = await bluez.wait_for_services(address)
    return bluez.BluezState(
        address=connected_state.address,
        visible=connected_state.visible,
        device=state.device,
        name=state.name or connected_state.name,
        paired=connected_state.paired,
        trusted=connected_state.trusted,
        connected=connected_state.connected,
        services_resolved=connected_state.services_resolved,
        bluetoothctl=connected_state.bluetoothctl,
        busctl=connected_state.busctl,
    )


async def main(address: str) -> None:
    print(f"Connecting to {address} ...")
    last_error: Exception | None = None
    for attempt in range(1, DISCOVERY_RETRY_ATTEMPTS + 1):
        try:
            state = await prepare_connection(address)
            target = state.device if state.device is not None else state.address
            async with BleakClient(target, timeout=20.0) as client:
                print(f"Connected: {client.is_connected}")
                if not client.is_connected:
                    raise RuntimeError("Failed to connect")

                print()
                print("Services and characteristics")
                print("=" * 100)

                for service in client.services:
                    print(f"[SERVICE] {service.uuid}  ({service.description})")
                    for char in service.characteristics:
                        print(f"  [CHAR] {char.uuid}")
                        print(f"         properties={props_to_str(char.properties)}")  # ty:ignore[invalid-argument-type]
                        print(f"         description={char.description}")

                        if "read" in char.properties:
                            try:
                                value = await client.read_gatt_char(char.uuid)
                                print(f"         value={value.hex()}  raw={value!r}")
                            except Exception as exc:
                                print(f"         read failed: {exc}")

                        for descriptor in char.descriptors:
                            print(
                                f"    [DESC] handle={descriptor.handle} uuid={descriptor.uuid}"
                            )
                            try:
                                dval = await client.read_gatt_descriptor(
                                    descriptor.handle
                                )
                                print(
                                    f"           value={bytes(dval).hex()} raw={bytes(dval)!r}"
                                )
                            except Exception as exc:
                                print(f"           read failed: {exc}")
                    print("-" * 100)
            return
        except Exception as exc:
            last_error = exc
            message = retry_message(exc, address)
            if attempt < DISCOVERY_RETRY_ATTEMPTS and message is not None:
                print(message)
                await asyncio.sleep(attempt)
                continue
            raise

    if last_error is not None:
        raise last_error


def cli() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <BLE_ADDRESS>")
        raise SystemExit(2)

    try:
        asyncio.run(main(sys.argv[1]))
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {format_cli_error(exc)}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
