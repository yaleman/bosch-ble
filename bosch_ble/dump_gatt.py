#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import sys

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import CharacteristicPropertyName


def props_to_str(props: list[str | "CharacteristicPropertyName"]) -> str:
    return ",".join(sorted(props))


async def main(address: str) -> None:
    print(f"Connecting to {address} ...")
    device = await BleakScanner.find_device_by_address(address, timeout=10.0)
    if device is None:
        raise RuntimeError(f"Device with address {address} was not found.")

    async with BleakClient(device, timeout=20.0) as client:
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
                        dval = await client.read_gatt_descriptor(descriptor.handle)
                        print(
                            f"           value={bytes(dval).hex()} raw={bytes(dval)!r}"
                        )
                    except Exception as exc:
                        print(f"           read failed: {exc}")
            print("-" * 100)


def cli() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <BLE_ADDRESS>")
        raise SystemExit(2)

    try:
        asyncio.run(main(sys.argv[1]))
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
