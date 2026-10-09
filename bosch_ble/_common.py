from __future__ import annotations

import re
from datetime import datetime
from collections.abc import Awaitable, Sequence
from typing import Any, Iterable, Protocol

BLE_ADDRESS_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def format_cli_error(exc: Exception) -> str:
    return str(exc) or type(exc).__name__


def normalize_address(address: str) -> str:
    return address.upper()


def normalize_uuid(value: object) -> str:
    return str(value).lower()


def validate_address(address: str) -> str:
    if not BLE_ADDRESS_RE.match(address):
        raise ValueError(
            f"{address!r} is not a valid BLE MAC address (expected AA:BB:CC:DD:EE:FF)"
        )
    return normalize_address(address)


class BleakDescriptor(Protocol):
    @property
    def handle(self) -> int: ...

    @property
    def uuid(self) -> str: ...


class BleakCharacteristic(Protocol):
    @property
    def uuid(self) -> str: ...

    @property
    def properties(self) -> Sequence[str]: ...

    @property
    def descriptors(self) -> Sequence[BleakDescriptor]: ...


class BleakService(Protocol):
    @property
    def uuid(self) -> str: ...

    @property
    def characteristics(self) -> Sequence[BleakCharacteristic]: ...


Services = Iterable[BleakService]


class SecurityClient(Protocol):
    @property
    def services(self) -> Services: ...

    @property
    def is_connected(self) -> bool: ...

    def pair(self) -> Awaitable[None]: ...

    def write_gatt_descriptor(self, handle: int, data: bytes, /) -> Awaitable[None]: ...


class BluezInterface(Protocol):
    def call_register_agent(self, path: str, capability: str) -> Awaitable[Any]: ...

    def call_request_default_agent(self, path: str) -> Awaitable[Any]: ...

    def call_unregister_agent(self, path: str) -> Awaitable[Any]: ...

    def call_pair(self) -> Awaitable[Any]: ...

    def call_set(self, interface: str, name: str, value: Any) -> Awaitable[Any]: ...
