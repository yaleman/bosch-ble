from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from bleak import BleakClient
from bleak.backends.device import BLEDevice

if TYPE_CHECKING:
    from bleak_esphome import APIConnectionManager


DEFAULT_ESPHOME_PORT = 6053
DEFAULT_CONNECT_TIMEOUT = 30.0
DEFAULT_SCAN_TIMEOUT = 10.0


@dataclass(frozen=True, slots=True)
class ESPHomeConfig:
    host: str
    port: int = DEFAULT_ESPHOME_PORT
    noise_psk: str | None = None


def get_esphome_config_from_env() -> ESPHomeConfig | None:
    host = os.environ.get("BOSCH_BLE_ESPHOME_HOST")
    if not host:
        return None
    return ESPHomeConfig(
        host=host,
        port=int(os.environ.get("BOSCH_BLE_ESPHOME_PORT", str(DEFAULT_ESPHOME_PORT))),
        noise_psk=os.environ.get("BOSCH_BLE_ESPHOME_NOISE_PSK"),
    )


@dataclass(slots=True)
class ESPHomeConnection:
    manager: APIConnectionManager


async def setup_esphome_proxy(config: ESPHomeConfig) -> ESPHomeConnection:
    from bleak_esphome import APIConnectionManager

    device_config = {
        "address": config.host,
        "noise_psk": config.noise_psk,
    }

    manager = APIConnectionManager(device_config)
    await manager.start()

    return ESPHomeConnection(manager=manager)


async def teardown_esphome_proxy(connection: ESPHomeConnection) -> None:
    try:
        await connection.manager.stop()
    except Exception:
        pass


@asynccontextmanager
async def esphome_proxy_context(config: ESPHomeConfig):
    connection = await setup_esphome_proxy(config)
    try:
        yield connection
    finally:
        await teardown_esphome_proxy(connection)


async def scan_via_esphome(
    config: ESPHomeConfig,
    *,
    timeout: float = DEFAULT_SCAN_TIMEOUT,
    detection_callback: Any = None,
) -> list[tuple[BLEDevice, Any]]:
    from bleak import BleakScanner

    async with esphome_proxy_context(config):
        scanner = BleakScanner(detection_callback=detection_callback)
        await scanner.start()
        try:
            await asyncio.sleep(timeout)
        finally:
            await scanner.stop()

        discovered: list[tuple[BLEDevice, Any]] = []
        for device, adv in scanner.discovered_devices_and_advertisement_data.items():
            discovered.append((device, adv))

        return discovered


@asynccontextmanager
async def esphome_bleak_client(
    config: ESPHomeConfig,
    address: str,
    *,
    timeout: float = DEFAULT_CONNECT_TIMEOUT,
):
    async with esphome_proxy_context(config):
        async with BleakClient(address, timeout=timeout) as client:
            yield client
