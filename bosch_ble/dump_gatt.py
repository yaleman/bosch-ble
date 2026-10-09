#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Iterable, Literal

from bleak import BleakClient
from bleak.backends.device import BLEDevice

from bosch_ble import bluez, esphome_proxy
from bosch_ble._common import (
    BleakDescriptor,
    format_cli_error,
    normalize_uuid,
    Services,
    SecurityClient,
    validate_address,
)

DISCOVERY_RETRY_ATTEMPTS = 3
REDISCOVERY_TIMEOUT = 10.0
BOSCH_SERVICE_UUID = "00000010-eaa2-11e9-81b4-2a2ae2dbcce4"
BOSCH_NOTIFY_CHAR_UUID = "00000011-eaa2-11e9-81b4-2a2ae2dbcce4"
CCCD_UUID = "00002902-0000-1000-8000-00805f9b34fb"

Backend = Literal["bluez", "esphome"]


class BoschSecurityDescriptorMissing(RuntimeError):
    """Raised when the Bosch CCCD security descriptor is absent on the device."""


def props_to_str(props: Iterable[object]) -> str:
    return ",".join(sorted(str(prop) for prop in props))


def retry_message(error: Exception, address: str) -> str | None:
    message = str(error).lower()
    if "failed to discover services" in message:
        return f"Retrying service discovery for {address} ..."
    if "operation already in progress" in message:
        return f"Retrying connection setup for {address} ..."
    if "security transition disconnected" in message:
        return f"Retrying security setup for {address} ..."
    return None


def find_bosch_security_descriptor(services: Services) -> BleakDescriptor:
    for service in services:
        if normalize_uuid(service.uuid) != BOSCH_SERVICE_UUID:
            continue
        for characteristic in service.characteristics:
            if normalize_uuid(characteristic.uuid) != BOSCH_NOTIFY_CHAR_UUID:
                continue
            for descriptor in characteristic.descriptors:
                if normalize_uuid(descriptor.uuid) == CCCD_UUID:
                    return descriptor
    raise BoschSecurityDescriptorMissing("Bosch security descriptor was not found.")


async def stage_bosch_security(
    client: SecurityClient,
    address: str,
    *,
    backend: Backend = "bluez",
) -> None:
    async def pair_with_agent() -> None:
        if backend == "bluez":
            async with bluez.pairing_agent(address):
                await client.pair()
        else:
            await client.pair()

    descriptor = find_bosch_security_descriptor(client.services)
    try:
        await client.write_gatt_descriptor(descriptor.handle, b"\x00\x00")
        return
    except Exception as exc:
        message = str(exc).lower()
        if "cannot write to cccd (0x2902) directly" in message:
            if backend == "bluez":
                state = bluez.read_device_state(address)
                if state.paired is True:
                    return
            await pair_with_agent()
            if backend == "bluez":
                state = await bluez.wait_for_state(
                    address,
                    paired=True,
                    connected=True,
                    services_resolved=True,
                )
                if state.connected is not True or not client.is_connected:
                    raise RuntimeError(f"Security transition disconnected for {address}.")
            return
        if "insufficient encryption" not in message and "authentication" not in message:
            raise

    await pair_with_agent()
    if backend == "bluez":
        state = await bluez.wait_for_state(
            address,
            paired=True,
            connected=True,
            services_resolved=True,
        )
        if state.connected is not True or not client.is_connected:
            raise RuntimeError(f"Security transition disconnected for {address}.")
    await client.write_gatt_descriptor(descriptor.handle, b"\x00\x00")


async def resolve_device(
    address: str,
    *,
    backend: Backend = "bluez",
) -> bluez.BluezState | None:
    if backend == "esphome":
        return None

    discovering = bluez.controller_discovering_state()
    print(f"ControllerDiscovering: {bluez.format_flag(discovering)}")
    bluez.assert_controller_ready(address, discovering=discovering)

    state = await bluez.preflight_device(address)
    bluez.print_preflight_summary(state)

    if state.device is None:
        print(f"Rediscovering {address} ...")
        state = await bluez.preflight_device(address, scan_timeout=REDISCOVERY_TIMEOUT)
        bluez.print_preflight_summary(state)

    return state


async def prepare_connection(
    address: str,
    *,
    backend: Backend = "bluez",
) -> bluez.BluezState | None:
    state = await resolve_device(address, backend=backend)
    if backend == "esphome":
        return None
    connected_state = await bluez.connect_device(address)
    return bluez.BluezState(
        address=connected_state.address,
        visible=connected_state.visible,
        device=connected_state.device if connected_state.device is not None else state.device if state else None,
        name=connected_state.name or (state.name if state else None),
        paired=connected_state.paired,
        trusted=connected_state.trusted,
        connected=connected_state.connected,
        services_resolved=connected_state.services_resolved,
        bluetoothctl=connected_state.bluetoothctl,
        busctl=connected_state.busctl,
    )


def client_target_for_state(state: bluez.BluezState | None) -> BLEDevice | str:
    if state is not None and state.device is not None:
        return state.device
    if state is not None:
        device_path = bluez.find_device_object_path(state.address)
        if device_path is not None:
            return BLEDevice(
                state.address,
                state.name,
                {"path": device_path},
            )
    if state is not None:
        return state.address
    raise RuntimeError("No device state available for client target")


async def main(
    address: str,
    *,
    backend: Backend = "bluez",
    esphome_host: str | None = None,
) -> None:
    print(f"Connecting to {address} via {backend} ...")
    last_error: Exception | None = None
    for attempt in range(1, DISCOVERY_RETRY_ATTEMPTS + 1):
        try:
            if backend == "esphome":
                if not esphome_host:
                    raise RuntimeError("ESPHome host is required for esphome backend")
                config = esphome_proxy.ESPHomeConfig(host=esphome_host)
                async with esphome_proxy.esphome_proxy_context(config):
                    async with BleakClient(address, timeout=20.0) as client:
                        print(f"Connected: {client.is_connected}")
                        if not client.is_connected:
                            raise RuntimeError("Failed to connect")
                        try:
                            await stage_bosch_security(client, address, backend=backend)
                        except BoschSecurityDescriptorMissing:
                            pass
                        except RuntimeError:
                            raise

                        print()
                        print("Services and characteristics")
                        print("=" * 100)

                        for service in client.services:
                            print(f"[SERVICE] {service.uuid}  ({service.description})")
                            for char in service.characteristics:
                                print(f"  [CHAR] {char.uuid}")
                                print(f"         properties={props_to_str(char.properties)}")
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
            else:
                state = await prepare_connection(address, backend=backend)
                target = client_target_for_state(state)
                async with BleakClient(target, timeout=20.0) as client:
                    print(f"Connected: {client.is_connected}")
                    if not client.is_connected:
                        raise RuntimeError("Failed to connect")
                    try:
                        await stage_bosch_security(client, address, backend=backend)
                    except BoschSecurityDescriptorMissing:
                        pass
                    except RuntimeError:
                        raise

                    print()
                    print("Services and characteristics")
                    print("=" * 100)

                    for service in client.services:
                        print(f"[SERVICE] {service.uuid}  ({service.description})")
                        for char in service.characteristics:
                            print(f"  [CHAR] {char.uuid}")
                            print(f"         properties={props_to_str(char.properties)}")
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
    parser = argparse.ArgumentParser(
        description="Connect to a Bosch eBike and dump GATT services/characteristics"
    )
    parser.add_argument("address", help="BLE address of the bike (XX:XX:XX:XX:XX:XX)")
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
        asyncio.run(main(address, backend=args.backend, esphome_host=args.esphome_host))
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {format_cli_error(exc)}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
