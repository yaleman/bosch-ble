from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from bleak.backends.device import BLEDevice

if TYPE_CHECKING:
    from bleak_esphome.backend.client import ESPHomeClientData


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
    client_data: ESPHomeClientData
    _cleanup: Any  # Callable[[], None]


async def setup_esphome_proxy(config: ESPHomeConfig) -> ESPHomeConnection:
    """Set up ESP32 proxy connection and return client_data for creating clients."""
    import habluetooth
    from aioesphomeapi import APIClient, ReconnectLogic
    from bleak_esphome import connect_scanner

    # Initialize habluetooth manager if not already set
    try:
        habluetooth.get_manager()
    except RuntimeError:
        # Manager not set, create and set it
        bt_manager = habluetooth.BluetoothManager()
        habluetooth.set_manager(bt_manager)

    # Create APIClient
    cli = APIClient(
        address=config.host,
        port=config.port,
        password=None,
        noise_psk=config.noise_psk,
    )

    # Track cleanup callbacks and connection state
    disconnect_callbacks: set[Any] = set()
    unsetup_scanner: Any = None
    unregister_scanner: Any = None
    client_data_holder: list[Any] = []  # Use list to allow mutation in closure
    connected_event = asyncio.Event()

    async def on_connect() -> None:
        nonlocal unsetup_scanner, unregister_scanner
        try:
            device_info = await cli.device_info()
            client_data = connect_scanner(cli, device_info, True)
            scanner = client_data.scanner
            assert scanner is not None
            unsetup_scanner = scanner.async_setup()
            unregister_scanner = habluetooth.get_manager().async_register_scanner(scanner)
            disconnect_callbacks.update(client_data.disconnect_callbacks)
            client_data_holder.append(client_data)
            connected_event.set()
        except Exception as e:
            print(f"Error in on_connect: {e}")
            raise

    async def on_disconnect(expected_disconnect: bool) -> None:
        nonlocal unsetup_scanner, unregister_scanner
        for callback in list(disconnect_callbacks):
            callback()
        disconnect_callbacks.clear()
        if unsetup_scanner is not None:
            unsetup_scanner()
            unsetup_scanner = None
        if unregister_scanner is not None:
            unregister_scanner()
            unregister_scanner = None
        connected_event.clear()

    # Create reconnect logic
    reconnect_logic = ReconnectLogic(
        client=cli,
        on_disconnect=on_disconnect,
        on_connect=on_connect,
    )

    # Start connection
    await reconnect_logic.start()

    # Wait for first connection
    try:
        await asyncio.wait_for(connected_event.wait(), timeout=DEFAULT_CONNECT_TIMEOUT)
    except asyncio.TimeoutError:
        await reconnect_logic.stop()
        raise RuntimeError(f"Timeout connecting to ESP32 proxy at {config.host}")

    if not client_data_holder:
        await reconnect_logic.stop()
        raise RuntimeError("No client_data received from ESP32 proxy")

    client_data = client_data_holder[0]

    def cleanup() -> None:
        asyncio.create_task(reconnect_logic.stop())

    return ESPHomeConnection(client_data=client_data, _cleanup=cleanup)


async def teardown_esphome_proxy(connection: ESPHomeConnection) -> None:
    try:
        connection._cleanup()
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
    """Scan for BLE devices via ESP32 proxy."""
    import habluetooth

    async with esphome_proxy_context(config):
        # Get the habluetooth manager that has the ESP32 scanner registered
        ha_manager = habluetooth.get_manager()
        
        # Wait for advertisements to come in
        await asyncio.sleep(timeout)
        
        # Get discovered devices from the manager
        discovered: list[tuple[BLEDevice, Any]] = []
        devices = ha_manager.async_discovered_devices(connectable=True)
        
        for device in devices:
            # Convert to BLEDevice format with required fields for ESPHomeClient
            bleak_device = BLEDevice(
                address=device.address,
                name=device.name,
                details={
                    "source": config.host,
                    "address_type": 0,  # PUBLIC address type
                },
            )
            discovered.append((bleak_device, None))
            
            if detection_callback:
                detection_callback(bleak_device, None)

        return discovered


@asynccontextmanager
async def esphome_bleak_client(
    config: ESPHomeConfig,
    address: str,
    *,
    timeout: float = DEFAULT_CONNECT_TIMEOUT,
    pair: bool = False,
):
    """Create a BLE client connected through the ESP32 proxy."""
    from bleak.backends.device import BLEDevice
    from bleak_esphome.backend.client import ESPHomeClient

    async with esphome_proxy_context(config) as conn:
        # Create a BLEDevice for the target address
        device = BLEDevice(
            address=address,
            name=None,
            details={"source": config.host, "address_type": 0},
        )
        
        # Create the ESPHomeClient using the client_data from the connection
        client = ESPHomeClient(device, client_data=conn.client_data, timeout=timeout)
        
        try:
            await client.connect(pair=pair)
            yield client
        finally:
            await client.disconnect()
