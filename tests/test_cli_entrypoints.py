from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bosch_ble import bluez, dump_gatt, log_chars, probe


class FakeDescriptor:
    def __init__(self, handle: int, uuid: str) -> None:
        self.handle = handle
        self.uuid = uuid


class FakeCharacteristicWithDescriptors:
    def __init__(self, uuid: str, properties: list[str], descriptors: list[FakeDescriptor]) -> None:
        self.uuid = uuid
        self.properties = properties
        self.descriptors = descriptors
        self.description = uuid


class FakeServiceWithCharacteristics:
    def __init__(self, uuid: str, characteristics: list[FakeCharacteristicWithDescriptors]) -> None:
        self.uuid = uuid
        self.characteristics = characteristics
        self.description = uuid


def test_dump_gatt_cli_shows_usage_without_address(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("sys.argv", ["bosch-ble-dump-gatt"]):
        with pytest.raises(SystemExit) as excinfo:
            dump_gatt.cli()

    assert excinfo.value.code == 2
    assert "Usage: bosch-ble-dump-gatt <BLE_ADDRESS>" in capsys.readouterr().out


def test_dump_gatt_cli_runs_async_main_with_address() -> None:
    async def fake_main(address: str) -> None:
        assert address == "AA:BB"

    with patch.object(dump_gatt, "main", side_effect=fake_main) as patched_main:
        with patch("sys.argv", ["bosch-ble-dump-gatt", "AA:BB"]):
            dump_gatt.cli()

    patched_main.assert_called_once_with("AA:BB")


def test_probe_cli_shows_usage_without_address(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("sys.argv", ["bosch-ble-probe"]):
        with pytest.raises(SystemExit) as excinfo:
            probe.cli()

    assert excinfo.value.code == 2
    assert "Usage: bosch-ble-probe <BLE_ADDRESS> [output_file]" in capsys.readouterr().out


def test_dump_gatt_cli_prints_friendly_error(capsys: pytest.CaptureFixture[str]) -> None:
    async def fake_main(address: str) -> None:
        raise RuntimeError(f"Device with address {address} was not found.")

    with patch.object(dump_gatt, "main", side_effect=fake_main):
        with patch("sys.argv", ["bosch-ble-dump-gatt", "AA:BB"]):
            with pytest.raises(SystemExit) as excinfo:
                dump_gatt.cli()

    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert captured.err == "Error: Device with address AA:BB was not found.\n"
    assert "Traceback" not in captured.err


def test_dump_gatt_cli_falls_back_to_exception_type_when_message_is_empty(
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_main(address: str) -> None:
        raise RuntimeError()

    with patch.object(dump_gatt, "main", side_effect=fake_main):
        with patch("sys.argv", ["bosch-ble-dump-gatt", "AA:BB"]):
            with pytest.raises(SystemExit) as excinfo:
                dump_gatt.cli()

    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert captured.err == "Error: RuntimeError\n"


def test_find_bosch_security_descriptor_returns_cccd_on_expected_handle() -> None:
    descriptor = FakeDescriptor(0x001F, "00002902-0000-1000-8000-00805f9b34fb")
    notify_char = FakeCharacteristicWithDescriptors(
        "00000011-eaa2-11e9-81b4-2a2ae2dbcce4",
        ["notify"],
        [descriptor],
    )
    write_char = FakeCharacteristicWithDescriptors(
        "00000012-eaa2-11e9-81b4-2a2ae2dbcce4",
        ["write-without-response"],
        [],
    )
    service = FakeServiceWithCharacteristics(
        "00000010-eaa2-11e9-81b4-2a2ae2dbcce4",
        [notify_char, write_char],
    )

    result = dump_gatt.find_bosch_security_descriptor([service])

    assert result is descriptor


def test_find_bosch_security_descriptor_fails_cleanly_when_service_is_missing() -> None:
    service = FakeServiceWithCharacteristics(
        "1800",
        [FakeCharacteristicWithDescriptors("2a00", ["read"], [])],
    )

    with pytest.raises(RuntimeError) as excinfo:
        dump_gatt.find_bosch_security_descriptor([service])

    assert str(excinfo.value) == "Bosch security descriptor was not found."


def test_stage_bosch_security_pairs_after_insufficient_encryption() -> None:
    events: list[tuple[str, object]] = []
    descriptor = FakeDescriptor(0x001F, "00002902-0000-1000-8000-00805f9b34fb")
    service = FakeServiceWithCharacteristics(
        "00000010-eaa2-11e9-81b4-2a2ae2dbcce4",
        [
            FakeCharacteristicWithDescriptors(
                "00000011-eaa2-11e9-81b4-2a2ae2dbcce4",
                ["notify"],
                [descriptor],
            )
        ],
    )

    class FakeClient:
        def __init__(self) -> None:
            self.services = [service]
            self.is_connected = True
            self.write_attempts = 0

        async def write_gatt_descriptor(self, handle: int, data: bytes) -> None:
            self.write_attempts += 1
            events.append(("write_gatt_descriptor", handle, data))
            if self.write_attempts == 1:
                raise RuntimeError("ATT error: Insufficient Encryption")

        async def pair(self) -> None:
            events.append(("pair", "called"))

    @asynccontextmanager
    async def fake_pairing_agent(_address: str):
        yield

    async def run() -> None:
        client = FakeClient()
        paired_state = bluez.BluezState(
            address="AA:BB",
            visible=True,
            device=None,
            name="sensor",
            paired=True,
            trusted=True,
            connected=True,
            services_resolved=True,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
        )
        with patch.object(
            dump_gatt.bluez,
            "wait_for_state",
            new=AsyncMock(return_value=paired_state),
        ) as wait_for_state:
            with patch.object(dump_gatt.bluez, "pairing_agent", fake_pairing_agent):
                await dump_gatt.stage_bosch_security(client, "AA:BB")

        wait_for_state.assert_awaited_once_with(
            "AA:BB",
            paired=True,
            connected=True,
            services_resolved=True,
        )

    asyncio.run(run())
    assert events == [
        ("write_gatt_descriptor", 0x001F, b"\x00\x00"),
        ("pair", "called"),
        ("write_gatt_descriptor", 0x001F, b"\x00\x00"),
    ]


def test_stage_bosch_security_skips_cccd_write_when_device_is_already_paired() -> None:
    events: list[tuple[str, object]] = []
    descriptor = FakeDescriptor(0x001F, "00002902-0000-1000-8000-00805f9b34fb")
    service = FakeServiceWithCharacteristics(
        "00000010-eaa2-11e9-81b4-2a2ae2dbcce4",
        [
            FakeCharacteristicWithDescriptors(
                "00000011-eaa2-11e9-81b4-2a2ae2dbcce4",
                ["notify"],
                [descriptor],
            )
        ],
    )

    class FakeClient:
        def __init__(self) -> None:
            self.services = [service]
            self.is_connected = True

        async def write_gatt_descriptor(self, handle: int, data: bytes) -> None:
            events.append(("write_gatt_descriptor", handle, data))
            raise RuntimeError("Cannot write to CCCD (0x2902) directly. Use start_notify() or stop_notify() instead.")

        async def pair(self) -> None:
            events.append(("pair", "called"))

    async def run() -> None:
        paired_state = bluez.BluezState(
            address="AA:BB",
            visible=False,
            device=None,
            name="sensor",
            paired=True,
            trusted=True,
            connected=True,
            services_resolved=True,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
        )
        with patch.object(dump_gatt.bluez, "read_device_state", return_value=paired_state):
            await dump_gatt.stage_bosch_security(FakeClient(), "AA:BB")

    asyncio.run(run())
    assert events == [("write_gatt_descriptor", 0x001F, b"\x00\x00")]


def test_stage_bosch_security_pairs_when_direct_cccd_write_is_blocked_on_unpaired_device() -> None:
    events: list[tuple[str, object]] = []
    descriptor = FakeDescriptor(0x001F, "00002902-0000-1000-8000-00805f9b34fb")
    service = FakeServiceWithCharacteristics(
        "00000010-eaa2-11e9-81b4-2a2ae2dbcce4",
        [
            FakeCharacteristicWithDescriptors(
                "00000011-eaa2-11e9-81b4-2a2ae2dbcce4",
                ["notify"],
                [descriptor],
            )
        ],
    )

    class FakeClient:
        def __init__(self) -> None:
            self.services = [service]
            self.is_connected = True

        async def write_gatt_descriptor(self, handle: int, data: bytes) -> None:
            events.append(("write_gatt_descriptor", handle, data))
            raise RuntimeError(
                "Cannot write to CCCD (0x2902) directly. Use start_notify() or stop_notify() instead."
            )

        async def pair(self) -> None:
            events.append(("pair", "called"))

    @asynccontextmanager
    async def fake_pairing_agent(_address: str):
        yield

    async def run() -> None:
        initial_state = bluez.BluezState(
            address="AA:BB",
            visible=False,
            device=None,
            name="sensor",
            paired=False,
            trusted=False,
            connected=True,
            services_resolved=False,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
        )
        paired_state = bluez.BluezState(
            address="AA:BB",
            visible=False,
            device=None,
            name="sensor",
            paired=True,
            trusted=True,
            connected=True,
            services_resolved=True,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
        )
        with patch.object(dump_gatt.bluez, "read_device_state", return_value=initial_state):
            with patch.object(
                dump_gatt.bluez,
                "wait_for_state",
                new=AsyncMock(return_value=paired_state),
            ) as wait_for_state:
                with patch.object(dump_gatt.bluez, "pairing_agent", fake_pairing_agent):
                    await dump_gatt.stage_bosch_security(FakeClient(), "AA:BB")

        wait_for_state.assert_awaited_once_with(
            "AA:BB",
            paired=True,
            connected=True,
            services_resolved=True,
        )

    asyncio.run(run())
    assert events == [
        ("write_gatt_descriptor", 0x001F, b"\x00\x00"),
        ("pair", "called"),
    ]


def test_assist_connection_accepts_connected_state_after_local_abort() -> None:
    info_result = CompletedProcess(["bluetoothctl", "info", "AA:BB"], 0, stdout="", stderr="")
    pair_result = CompletedProcess(["bluetoothctl", "pair", "AA:BB"], 0, stdout="", stderr="")
    trust_result = CompletedProcess(["bluetoothctl", "trust", "AA:BB"], 0, stdout="", stderr="")
    connect_result = CompletedProcess(
        ["bluetoothctl", "connect", "AA:BB"],
        1,
        stdout="Connected: yes\n",
        stderr="Failed to connect: org.bluez.Error.Failed le-connection-abort-by-local\n",
    )
    connected_state = bluez.BluezState(
        address="AA:BB",
        visible=True,
        device=None,
        name="sensor",
        paired=False,
        trusted=True,
        connected=True,
        services_resolved=None,
        bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="Connected: yes\n", stderr=""),
        busctl=None,
    )

    @asynccontextmanager
    async def fake_pairing_agent(address: str):
        yield

    async def run() -> None:
        with patch.object(
            bluez,
            "run_command_async",
            side_effect=[info_result, pair_result, trust_result, connect_result],
        ):
            with patch.object(bluez, "pairing_agent", side_effect=fake_pairing_agent):
                with patch.object(bluez, "read_device_state", return_value=connected_state):
                    result = await bluez.assist_connection("AA:BB")

        assert result is connected_state

    asyncio.run(run())


def test_assist_connection_runs_pair_trust_connect_inside_pairing_agent() -> None:
    events: list[object] = []
    info_result = CompletedProcess(["bluetoothctl", "info", "AA:BB"], 0, stdout="", stderr="")
    pair_result = CompletedProcess(["bluetoothctl", "pair", "AA:BB"], 0, stdout="", stderr="")
    trust_result = CompletedProcess(["bluetoothctl", "trust", "AA:BB"], 0, stdout="", stderr="")
    connect_result = CompletedProcess(["bluetoothctl", "connect", "AA:BB"], 0, stdout="Connected: yes\n", stderr="")
    connected_state = bluez.BluezState(
        address="AA:BB",
        visible=True,
        device=None,
        name="sensor",
        paired=True,
        trusted=True,
        connected=True,
        services_resolved=None,
        bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="Connected: yes\n", stderr=""),
        busctl=None,
    )

    @asynccontextmanager
    async def fake_pairing_agent(address: str):
        events.append(("agent_enter", address))
        try:
            yield
        finally:
            events.append(("agent_exit", address))

    async def run() -> None:
        async def fake_run_command(argv: list[str], timeout: float = 15.0) -> CompletedProcess[str]:
            events.append(tuple(argv))
            results = {
                ("bluetoothctl", "info", "AA:BB"): info_result,
                ("bluetoothctl", "pair", "AA:BB"): pair_result,
                ("bluetoothctl", "trust", "AA:BB"): trust_result,
                ("bluetoothctl", "connect", "AA:BB"): connect_result,
            }
            return results[tuple(argv)]

        with patch.object(bluez, "pairing_agent", side_effect=fake_pairing_agent):
            with patch.object(bluez, "run_command_async", side_effect=fake_run_command):
                with patch.object(bluez, "read_device_state", return_value=connected_state):
                    result = await bluez.assist_connection("AA:BB")

        assert result is connected_state

    asyncio.run(run())
    assert events == [
        ("bluetoothctl", "info", "AA:BB"),
        ("agent_enter", "AA:BB"),
        ("bluetoothctl", "pair", "AA:BB"),
        ("bluetoothctl", "trust", "AA:BB"),
        ("bluetoothctl", "connect", "AA:BB"),
        ("agent_exit", "AA:BB"),
    ]


def test_assist_connection_skips_pair_and_trust_when_device_is_already_bonded() -> None:
    events: list[object] = []
    info_result = CompletedProcess(
        ["bluetoothctl", "info", "AA:BB"],
        0,
        stdout="Paired: yes\nTrusted: yes\nConnected: no\n",
        stderr="",
    )
    connect_result = CompletedProcess(["bluetoothctl", "connect", "AA:BB"], 0, stdout="Connected: yes\n", stderr="")
    connected_state = bluez.BluezState(
        address="AA:BB",
        visible=True,
        device=None,
        name="sensor",
        paired=True,
        trusted=True,
        connected=True,
        services_resolved=None,
        bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="Connected: yes\n", stderr=""),
        busctl=None,
    )

    @asynccontextmanager
    async def fake_pairing_agent(address: str):
        events.append(("agent_enter", address))
        try:
            yield
        finally:
            events.append(("agent_exit", address))

    async def run() -> None:
        async def fake_run_command(argv: list[str], timeout: float = 15.0) -> CompletedProcess[str]:
            events.append(tuple(argv))
            results = {
                ("bluetoothctl", "info", "AA:BB"): info_result,
                ("bluetoothctl", "connect", "AA:BB"): connect_result,
            }
            return results[tuple(argv)]

        with patch.object(bluez, "pairing_agent", side_effect=fake_pairing_agent):
            with patch.object(bluez, "run_command_async", side_effect=fake_run_command):
                with patch.object(bluez, "read_device_state", return_value=connected_state):
                    result = await bluez.assist_connection("AA:BB")

        assert result is connected_state

    asyncio.run(run())
    assert events == [
        ("bluetoothctl", "info", "AA:BB"),
        ("agent_enter", "AA:BB"),
        ("bluetoothctl", "connect", "AA:BB"),
        ("agent_exit", "AA:BB"),
    ]


def test_assist_connection_fails_when_pair_fails_and_device_remains_unpaired() -> None:
    info_result = CompletedProcess(
        ["bluetoothctl", "info", "AA:BB"],
        0,
        stdout="Paired: no\nTrusted: no\nConnected: no\n",
        stderr="",
    )
    pair_result = CompletedProcess(
        ["bluetoothctl", "pair", "AA:BB"],
        1,
        stdout="",
        stderr="Failed to pair: org.bluez.Error.AuthenticationCanceled\n",
    )
    unpaired_state = bluez.BluezState(
        address="AA:BB",
        visible=True,
        device=None,
        name="sensor",
        paired=False,
        trusted=False,
        connected=False,
        services_resolved=None,
        bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="Paired: no\n", stderr=""),
        busctl=None,
    )

    @asynccontextmanager
    async def fake_pairing_agent(_address: str):
        yield

    async def run() -> None:
        with patch.object(
            bluez,
            "run_command_async",
            side_effect=[info_result, pair_result],
        ):
            with patch.object(bluez, "pairing_agent", side_effect=fake_pairing_agent):
                with patch.object(bluez, "read_device_state", return_value=unpaired_state):
                    with pytest.raises(RuntimeError, match="BlueZ pair failed for AA:BB"):
                        await bluez.assist_connection("AA:BB")

    asyncio.run(run())


def test_dump_gatt_main_runs_preflight_and_assisted_connect_before_bleak_client(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeClient:
        def __init__(self, address_or_ble_device, timeout: float = 20.0) -> None:
            call_order.append(("bleak_client", address_or_ble_device))
            self.address_or_ble_device = address_or_ble_device
            self.timeout = timeout
            self.is_connected = True
            self.services = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    fake_device = object()
    call_order: list[tuple[str, object]] = []

    async def run() -> None:
        preflight_state = bluez.BluezState(
            address="AA:BB",
            visible=True,
            device=fake_device,
            name="sensor",
            paired=False,
            trusted=False,
            connected=False,
            services_resolved=False,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
        )
        connected_state = bluez.BluezState(
            address="AA:BB",
            visible=True,
            device=fake_device,
            name="sensor",
            paired=False,
            trusted=True,
            connected=True,
            services_resolved=False,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
        )
        with patch.object(
            dump_gatt.bluez,
            "preflight_device",
            new=AsyncMock(side_effect=lambda address: call_order.append(("preflight", address)) or preflight_state),
        ):
            with patch.object(
                dump_gatt.bluez,
                "assist_connection",
                new=AsyncMock(side_effect=lambda address: call_order.append(("assist_connection", address)) or connected_state),
            ):
                with patch.object(dump_gatt, "BleakClient", FakeClient):
                    await dump_gatt.main("AA:BB")

    asyncio.run(run())
    assert "Connecting to AA:BB ..." in capsys.readouterr().out
    assert call_order == [
        ("preflight", "AA:BB"),
        ("assist_connection", "AA:BB"),
        ("bleak_client", fake_device),
    ]


def test_dump_gatt_main_can_connect_by_address_when_scan_cannot_find_device(
    capsys: pytest.CaptureFixture[str],
) -> None:
    targets: list[object] = []

    class FakeClient:
        def __init__(self, address_or_ble_device, timeout: float = 20.0) -> None:
            targets.append(address_or_ble_device)
            self.address_or_ble_device = address_or_ble_device
            self.timeout = timeout
            self.is_connected = True
            self.services = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    async def run() -> None:
        missing_state = bluez.BluezState(
            address="AA:BB",
            visible=False,
            device=None,
            name=None,
            paired=None,
            trusted=None,
            connected=None,
            services_resolved=None,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="not available\n", stderr=""),
            busctl=None,
        )
        connected_state = bluez.BluezState(
            address="AA:BB",
            visible=False,
            device=None,
            name="sensor",
            paired=False,
            trusted=True,
            connected=True,
            services_resolved=True,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
        )
        with patch.object(
            dump_gatt.bluez,
            "preflight_device",
            new=AsyncMock(return_value=missing_state),
        ):
            with patch.object(
                dump_gatt.bluez,
                "assist_connection",
                new=AsyncMock(return_value=connected_state),
            ):
                with patch.object(dump_gatt, "BleakClient", FakeClient):
                    await dump_gatt.main("AA:BB")

    asyncio.run(run())
    assert targets == ["AA:BB"]
    output = capsys.readouterr().out
    assert "Connecting to AA:BB ..." in output


def test_dump_gatt_main_uses_bluez_device_path_when_connected_but_not_visible(
    capsys: pytest.CaptureFixture[str],
) -> None:
    targets: list[object] = []

    class FakeClient:
        def __init__(self, address_or_ble_device, timeout: float = 20.0) -> None:
            targets.append(address_or_ble_device)
            self.address_or_ble_device = address_or_ble_device
            self.timeout = timeout
            self.is_connected = True
            self.services = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    async def run() -> None:
        missing_state = bluez.BluezState(
            address="AA:BB",
            visible=False,
            device=None,
            name="sensor",
            paired=True,
            trusted=True,
            connected=True,
            services_resolved=True,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
        )
        with patch.object(
            dump_gatt.bluez,
            "preflight_device",
            new=AsyncMock(return_value=missing_state),
        ):
            with patch.object(
                dump_gatt.bluez,
                "assist_connection",
                new=AsyncMock(return_value=missing_state),
            ):
                with patch.object(
                    dump_gatt.bluez,
                    "find_device_object_path",
                    return_value="/org/bluez/hci0/dev_AA_BB",
                ):
                    with patch.object(dump_gatt, "BleakClient", FakeClient):
                        await dump_gatt.main("AA:BB")

    asyncio.run(run())
    assert len(targets) == 1
    assert getattr(targets[0], "address", None) == "AA:BB"
    assert getattr(targets[0], "details", {}).get("path") == "/org/bluez/hci0/dev_AA_BB"
    output = capsys.readouterr().out
    assert "Connecting to AA:BB ..." in output


def test_dump_gatt_main_skips_wait_when_service_resolution_is_unavailable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    targets: list[object] = []
    fake_device = object()

    class FakeClient:
        def __init__(self, address_or_ble_device, timeout: float = 20.0) -> None:
            targets.append(address_or_ble_device)
            self.address_or_ble_device = address_or_ble_device
            self.timeout = timeout
            self.is_connected = True
            self.services = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    async def run() -> None:
        preflight_state = bluez.BluezState(
            address="AA:BB",
            visible=True,
            device=fake_device,
            name="sensor",
            paired=False,
            trusted=False,
            connected=False,
            services_resolved=None,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=None,
        )
        connected_state = bluez.BluezState(
            address="AA:BB",
            visible=True,
            device=fake_device,
            name="sensor",
            paired=False,
            trusted=True,
            connected=True,
            services_resolved=None,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=None,
        )
        wait_for_services = AsyncMock(return_value=connected_state)
        with patch.object(
            dump_gatt.bluez,
            "preflight_device",
            new=AsyncMock(return_value=preflight_state),
        ):
            with patch("bosch_ble.bluez.shutil.which", return_value=None):
                with patch.object(
                    dump_gatt.bluez,
                    "assist_connection",
                    new=AsyncMock(return_value=connected_state),
                ):
                    with patch.object(
                        dump_gatt.bluez,
                        "wait_for_services",
                        new=wait_for_services,
                    ):
                        with patch.object(dump_gatt, "BleakClient", FakeClient):
                            await dump_gatt.main("AA:BB")

        wait_for_services.assert_not_called()

    asyncio.run(run())
    assert targets == [fake_device]
    assert "Connecting to AA:BB ..." in capsys.readouterr().out


def test_dump_gatt_main_retries_when_service_discovery_disconnects(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeClient:
        attempts = 0

        def __init__(self, address_or_ble_device, timeout: float = 20.0) -> None:
            self.address_or_ble_device = address_or_ble_device
            self.timeout = timeout
            self.is_connected = True
            self.services = []

        async def __aenter__(self):
            type(self).attempts += 1
            if type(self).attempts == 1:
                raise RuntimeError("failed to discover services, device disconnected")
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    async def run() -> None:
        ready_state = bluez.BluezState(
            address="AA:BB",
            visible=True,
            device=object(),
            name="sensor",
            paired=False,
            trusted=True,
            connected=True,
            services_resolved=True,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
        )
        with patch.object(dump_gatt.bluez, "preflight_device", new=AsyncMock(return_value=ready_state)):
            with patch.object(dump_gatt.bluez, "assist_connection", new=AsyncMock(return_value=ready_state)):
                with patch.object(dump_gatt.bluez, "wait_for_services", new=AsyncMock(return_value=ready_state)):
                    with patch.object(dump_gatt, "BleakClient", FakeClient):
                        await dump_gatt.main("AA:BB")

    asyncio.run(run())
    output = capsys.readouterr().out
    assert "Connecting to AA:BB ..." in output


def test_prepare_connection_accepts_connected_state_when_services_do_not_resolve() -> None:
    async def run() -> None:
        preflight_state = bluez.BluezState(
            address="AA:BB",
            visible=True,
            device=object(),
            name="sensor",
            paired=True,
            trusted=True,
            connected=False,
            services_resolved=False,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
        )
        connected_state = bluez.BluezState(
            address="AA:BB",
            visible=True,
            device=object(),
            name="sensor",
            paired=True,
            trusted=True,
            connected=True,
            services_resolved=False,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
        )
        with patch.object(dump_gatt, "resolve_device", new=AsyncMock(return_value=preflight_state)):
            with patch.object(dump_gatt.bluez, "assist_connection", new=AsyncMock(return_value=connected_state)):
                state = await dump_gatt.prepare_connection("AA:BB")

        assert state.address == "AA:BB"
        assert state.connected is True
        assert state.services_resolved is False

    asyncio.run(run())


def test_log_chars_main_uses_dump_gatt_client_target_for_state(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    targets: list[object] = []
    notify_callbacks: list[object] = []
    target = object()
    descriptor = FakeDescriptor(0x001F, "00002902-0000-1000-8000-00805f9b34fb")
    service = FakeServiceWithCharacteristics(
        "00000010-eaa2-11e9-81b4-2a2ae2dbcce4",
        [FakeCharacteristicWithDescriptors("00000011-eaa2-11e9-81b4-2a2ae2dbcce4", ["notify"], [descriptor])],
    )

    class FakeClient:
        def __init__(self, address_or_ble_device, timeout: float = 20.0) -> None:
            targets.append(address_or_ble_device)
            self.address_or_ble_device = address_or_ble_device
            self.timeout = timeout
            self.is_connected = True
            self.services = [service]

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def start_notify(self, uuid: str, callback) -> None:
            notify_callbacks.append(callback)

        async def stop_notify(self, uuid: str) -> None:
            return None

        async def read_gatt_char(self, uuid: str) -> bytearray:
            return bytearray()

    async def fake_sleep(delay: float) -> None:
        log_chars.STOP.set()

    async def run() -> None:
        state = bluez.BluezState(
            address="AA:BB",
            visible=False,
            device=None,
            name="sensor",
            paired=True,
            trusted=True,
            connected=True,
            services_resolved=True,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
        )
        with patch.object(log_chars.live.dump_gatt, "prepare_connection", new=AsyncMock(return_value=state)):
            with patch.object(log_chars.live.dump_gatt, "client_target_for_state", return_value=target):
                with patch.object(log_chars.live.dump_gatt, "stage_bosch_security", new=AsyncMock()):
                    with patch.object(log_chars.live, "BleakClient", FakeClient):
                        with patch.object(log_chars.asyncio, "sleep", side_effect=fake_sleep):
                            await log_chars.main("AA:BB", str(tmp_path / "ble_log.txt"))

    asyncio.run(run())
    assert targets == [target]
    output = capsys.readouterr().out
    assert "Connecting to AA:BB ..." in output
    assert "Connected: True" in output
    assert "Subscribing to notifiable characteristics..." in output


def test_probe_main_uses_dump_gatt_target_and_logs_probe_results(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    targets: list[object] = []
    writes: list[tuple[str, bytes, bool]] = []
    callbacks: dict[str, object] = {}
    target = object()

    notify_char = FakeCharacteristicWithDescriptors(
        "00000011-eaa2-11e9-81b4-2a2ae2dbcce4",
        ["notify"],
        [FakeDescriptor(0x001F, "00002902-0000-1000-8000-00805f9b34fb")],
    )
    write_char = FakeCharacteristicWithDescriptors(
        "00000012-eaa2-11e9-81b4-2a2ae2dbcce4",
        ["write-without-response"],
        [],
    )
    read_char = FakeCharacteristicWithDescriptors(
        "00000041-eaa2-11e9-81b4-2a2ae2dbcce4",
        ["read"],
        [],
    )
    services = [
        FakeServiceWithCharacteristics(
            "00000010-eaa2-11e9-81b4-2a2ae2dbcce4",
            [notify_char, write_char],
        ),
        FakeServiceWithCharacteristics(
            "00000040-eaa2-11e9-81b4-2a2ae2dbcce4",
            [read_char],
        ),
    ]

    class FakeClient:
        def __init__(self, address_or_ble_device, timeout: float = 20.0) -> None:
            targets.append(address_or_ble_device)
            self.address_or_ble_device = address_or_ble_device
            self.timeout = timeout
            self.is_connected = True
            self.services = services
            self.read_values = {
                "00000041-eaa2-11e9-81b4-2a2ae2dbcce4": bytearray(b"\x18\x00"),
            }

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def start_notify(self, uuid: str, callback) -> None:
            callbacks[uuid] = callback

        async def stop_notify(self, uuid: str) -> None:
            return None

        async def read_gatt_char(self, uuid: str) -> bytearray:
            return self.read_values[uuid]

        async def write_gatt_char(self, uuid: str, data: bytes, response: bool = False) -> None:
            writes.append((uuid, data, response))
            self.read_values["00000041-eaa2-11e9-81b4-2a2ae2dbcce4"] = bytearray(b"\x19\x00")
            callback = callbacks["00000011-eaa2-11e9-81b4-2a2ae2dbcce4"]
            callback("notify-sender", bytearray(b"\x10\x02"))

    async def fake_sleep(delay: float) -> None:
        return None

    async def run() -> None:
        state = bluez.BluezState(
            address="AA:BB",
            visible=False,
            device=None,
            name="sensor",
            paired=True,
            trusted=True,
            connected=True,
            services_resolved=True,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
        )
        with patch.object(probe.live.dump_gatt, "prepare_connection", new=AsyncMock(return_value=state)):
            with patch.object(probe.live.dump_gatt, "client_target_for_state", return_value=target):
                with patch.object(probe.live.dump_gatt, "stage_bosch_security", new=AsyncMock()):
                    with patch.object(probe.live, "BleakClient", FakeClient):
                        with patch.object(probe.asyncio, "sleep", side_effect=fake_sleep):
                            with patch.object(probe, "PROBE_TARGET_UUIDS", ("00000012-eaa2-11e9-81b4-2a2ae2dbcce4",)):
                                with patch.object(probe, "PROBE_PAYLOADS", (b"\x01",)):
                                    await probe.main("AA:BB", str(tmp_path / "probe.log"))

    asyncio.run(run())
    assert targets == [target]
    assert writes == [("00000012-eaa2-11e9-81b4-2a2ae2dbcce4", b"\x01", False)]
    output = capsys.readouterr().out
    assert "Connecting to AA:BB ..." in output
    assert "PROBE uuid=00000012-eaa2-11e9-81b4-2a2ae2dbcce4 payload=01" in output
    assert "NOTIFY sender=notify-sender hex=1002" in output
    assert "READ_CHANGE uuid=00000041-eaa2-11e9-81b4-2a2ae2dbcce4 before=1800 after=1900" in output


def test_dump_gatt_main_retries_when_bluez_reports_operation_in_progress(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FakeClient:
        attempts = 0

        def __init__(self, address_or_ble_device, timeout: float = 20.0) -> None:
            self.address_or_ble_device = address_or_ble_device
            self.timeout = timeout
            self.is_connected = True
            self.services = []

        async def __aenter__(self):
            type(self).attempts += 1
            if type(self).attempts == 1:
                raise RuntimeError("failed to discover services, device disconnected")
            if type(self).attempts == 2:
                raise RuntimeError("[org.bluez.Error.Failed] Operation already in progress")
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    async def run() -> None:
        ready_state = bluez.BluezState(
            address="AA:BB",
            visible=True,
            device=object(),
            name="sensor",
            paired=False,
            trusted=True,
            connected=True,
            services_resolved=True,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
        )
        with patch.object(dump_gatt.bluez, "preflight_device", new=AsyncMock(return_value=ready_state)):
            with patch.object(dump_gatt.bluez, "assist_connection", new=AsyncMock(return_value=ready_state)):
                with patch.object(dump_gatt.bluez, "wait_for_services", new=AsyncMock(return_value=ready_state)):
                    with patch.object(dump_gatt, "BleakClient", FakeClient):
                        await dump_gatt.main("AA:BB")

    asyncio.run(run())
    output = capsys.readouterr().out
    assert "Retrying service discovery for AA:BB ..." in output
    assert "Retrying connection setup for AA:BB ..." in output


def test_dump_gatt_main_fails_cleanly_when_bluez_connect_fails() -> None:
    async def run() -> None:
        preflight_state = bluez.BluezState(
            address="AA:BB",
            visible=True,
            device=object(),
            name="sensor",
            paired=False,
            trusted=False,
            connected=False,
            services_resolved=False,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
        )
        with patch.object(dump_gatt.bluez, "preflight_device", new=AsyncMock(return_value=preflight_state)):
            with patch.object(
                dump_gatt.bluez,
                "assist_connection",
                new=AsyncMock(side_effect=RuntimeError("BlueZ connect failed for AA:BB: le-connection-abort-by-local")),
            ):
                with pytest.raises(RuntimeError) as excinfo:
                    await dump_gatt.main("AA:BB")

        assert str(excinfo.value) == "BlueZ connect failed for AA:BB: le-connection-abort-by-local"

    asyncio.run(run())


def test_dump_gatt_main_fails_when_bleak_service_discovery_disconnects() -> None:
    async def run() -> None:
        preflight_state = bluez.BluezState(
            address="AA:BB",
            visible=True,
            device=object(),
            name="sensor",
            paired=False,
            trusted=True,
            connected=False,
            services_resolved=False,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
        )
        connected_state = bluez.BluezState(
            address="AA:BB",
            visible=True,
            device=preflight_state.device,
            name="sensor",
            paired=False,
            trusted=True,
            connected=True,
            services_resolved=False,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
        )
        with patch.object(dump_gatt.bluez, "preflight_device", new=AsyncMock(return_value=preflight_state)):
            with patch.object(dump_gatt.bluez, "assist_connection", new=AsyncMock(return_value=connected_state)):
                with patch.object(dump_gatt, "BleakClient", side_effect=RuntimeError("failed to discover services, device disconnected")):
                    with pytest.raises(RuntimeError) as excinfo:
                        await dump_gatt.main("AA:BB")

        assert str(excinfo.value) == "failed to discover services, device disconnected"

    asyncio.run(run())


def test_log_chars_cli_shows_usage_without_address(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("sys.argv", ["bosch-ble-log-chars"]):
        with pytest.raises(SystemExit) as excinfo:
            log_chars.cli()

    assert excinfo.value.code == 2
    assert "Usage: bosch-ble-log-chars <BLE_ADDRESS> [output_file]" in capsys.readouterr().out


def test_log_chars_cli_runs_async_main_with_default_output() -> None:
    async def fake_main(address: str, out_file: str) -> None:
        assert address == "AA:BB"
        assert out_file == "ble_log.txt"

    with patch.object(log_chars, "main", side_effect=fake_main) as patched_main:
        with patch("sys.argv", ["bosch-ble-log-chars", "AA:BB"]):
            log_chars.cli()

    patched_main.assert_called_once_with("AA:BB", "ble_log.txt")


def test_log_chars_cli_runs_async_main_with_explicit_output() -> None:
    async def fake_main(address: str, out_file: str) -> None:
        assert address == "AA:BB"
        assert out_file == "out.txt"

    with patch.object(log_chars, "main", side_effect=fake_main) as patched_main:
        with patch("sys.argv", ["bosch-ble-log-chars", "AA:BB", "out.txt"]):
            log_chars.cli()

    patched_main.assert_called_once_with("AA:BB", "out.txt")


def test_log_chars_main_resets_stop_event_between_runs(
    tmp_path: Path,
) -> None:
    read_events: list[str] = []
    prepared_targets: list[object] = []

    prepared_state = bluez.BluezState(
        address="AA:BB",
        visible=True,
        device=object(),
        name="sensor",
        paired=False,
        trusted=True,
        connected=True,
        services_resolved=True,
        bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
        busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
    )

    class FakeCharacteristic:
        uuid = "1234"
        properties = ["read"]

    class FakeService:
        characteristics = [FakeCharacteristic()]

    class FakeClient:
        def __init__(self, address_or_ble_device, timeout: float = 20.0) -> None:
            prepared_targets.append(address_or_ble_device)
            self.address = address_or_ble_device
            self.timeout = timeout
            self.is_connected = True
            self.services = [FakeService()]

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def read_gatt_char(self, uuid: str) -> bytes:
            read_events.append(uuid)
            return b"\x01"

    async def fake_sleep(delay: float) -> None:
        log_chars.STOP.set()

    async def run_once() -> None:
        with patch.object(log_chars.live, "BleakClient", FakeClient):
            with patch.object(
                log_chars.live.dump_gatt,
                "prepare_connection",
                new=AsyncMock(return_value=prepared_state),
            ):
                with patch.object(
                    log_chars.asyncio,
                    "sleep",
                    new=AsyncMock(side_effect=fake_sleep),
                ):
                    await log_chars.main("AA:BB", str(tmp_path / "ble_log.txt"))

    asyncio.run(run_once())
    asyncio.run(run_once())

    assert read_events == ["1234", "1234"]
    assert prepared_targets == [prepared_state.device, prepared_state.device]


def test_log_chars_main_prepares_connection_before_bleak_client(
    tmp_path: Path,
) -> None:
    fake_device = object()
    targets: list[object] = []
    prepared_state = bluez.BluezState(
        address="AA:BB",
        visible=True,
        device=fake_device,
        name="sensor",
        paired=False,
        trusted=True,
        connected=True,
        services_resolved=True,
        bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
        busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
    )

    class FakeCharacteristic:
        uuid = "1234"
        properties = ["read"]

    class FakeService:
        characteristics = [FakeCharacteristic()]

    class FakeClient:
        def __init__(self, address_or_ble_device, timeout: float = 20.0) -> None:
            targets.append(address_or_ble_device)
            self.is_connected = True
            self.services = [FakeService()]

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def read_gatt_char(self, uuid: str) -> bytes:
            return b"\x01"

    async def fake_sleep(delay: float) -> None:
        log_chars.STOP.set()

    async def run() -> None:
        with patch.object(log_chars.live, "BleakClient", FakeClient):
            with patch.object(
                log_chars.live.dump_gatt,
                "prepare_connection",
                new=AsyncMock(return_value=prepared_state),
            ) as prepare_connection:
                with patch.object(
                    log_chars.asyncio,
                    "sleep",
                    new=AsyncMock(side_effect=fake_sleep),
                ):
                    await log_chars.main("AA:BB", str(tmp_path / "ble_log.txt"))

        prepare_connection.assert_awaited_once_with("AA:BB")

    asyncio.run(run())
    assert targets == [fake_device]


def test_bluez_preflight_cli_shows_usage_without_address(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch("sys.argv", ["bosch-ble-bluez-preflight"]):
        with pytest.raises(SystemExit) as excinfo:
            bluez.preflight_cli()

    assert excinfo.value.code == 2
    assert "Usage: bosch-ble-bluez-preflight <BLE_ADDRESS>" in capsys.readouterr().out


def test_bluez_preflight_cli_reports_visible_device_and_state(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_device = SimpleNamespace(name="sensor")

    def fake_run(argv: list[str], timeout: float = 0.0) -> CompletedProcess[str]:
        if argv[:2] == ["bluetoothctl", "info"]:
            return CompletedProcess(
                argv,
                0,
                stdout="Paired: no\nTrusted: yes\nConnected: yes\n",
                stderr="",
            )
        if argv[:2] == ["busctl", "tree"]:
            return CompletedProcess(
                argv,
                0,
                stdout="/org/bluez/hci1/dev_AA_BB\n",
                stderr="",
            )
        if argv[:2] == ["busctl", "introspect"]:
            assert argv[3] == "/org/bluez/hci1/dev_AA_BB"
            return CompletedProcess(
                argv,
                0,
                stdout=".ServicesResolved  property  b  true\n",
                stderr="",
            )
        raise AssertionError(argv)

    with patch.object(bluez, "run_command", side_effect=fake_run):
        with patch.object(
            bluez.BleakScanner,
            "find_device_by_address",
            new=AsyncMock(return_value=fake_device),
        ):
            with patch("bosch_ble.bluez.shutil.which", return_value="/usr/bin/busctl"):
                with patch("sys.argv", ["bosch-ble-bluez-preflight", "AA:BB"]):
                    bluez.preflight_cli()

    output = capsys.readouterr().out
    assert "== preflight ==" in output
    assert "Visible: yes" in output
    assert "Name: sensor" in output
    assert "Trusted: yes" in output
    assert "ServicesResolved: yes" in output


def test_bluez_preflight_cli_reads_services_resolved_from_tree_output_with_prefixes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_run(argv: list[str], timeout: float = 0.0) -> CompletedProcess[str]:
        if argv[:2] == ["bluetoothctl", "info"]:
            return CompletedProcess(
                argv,
                0,
                stdout="Paired: yes\nTrusted: yes\nConnected: yes\n",
                stderr="",
            )
        if argv[:2] == ["busctl", "tree"]:
            return CompletedProcess(
                argv,
                0,
                stdout="└─ /org/bluez/hci0\n   └─ /org/bluez/hci0/dev_AA_BB\n",
                stderr="",
            )
        if argv[:2] == ["busctl", "introspect"]:
            return CompletedProcess(
                argv,
                0,
                stdout=".ServicesResolved  property  b  true\n",
                stderr="",
            )
        raise AssertionError(argv)

    with patch.object(bluez, "run_command", side_effect=fake_run):
        with patch.object(
            bluez.BleakScanner,
            "find_device_by_address",
            new=AsyncMock(return_value=None),
        ):
            with patch("bosch_ble.bluez.shutil.which", return_value="/usr/bin/busctl"):
                with patch("sys.argv", ["bosch-ble-bluez-preflight", "AA:BB"]):
                    bluez.preflight_cli()

    output = capsys.readouterr().out
    assert "ServicesResolved: yes" in output
    assert "== busctl introspect ==" in output


def test_bluez_preflight_cli_falls_back_when_busctl_tree_with_path_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], timeout: float = 0.0) -> CompletedProcess[str]:
        calls.append(argv)
        if argv[:2] == ["bluetoothctl", "info"]:
            return CompletedProcess(
                argv,
                0,
                stdout="Paired: yes\nTrusted: yes\nConnected: yes\n",
                stderr="",
            )
        if argv == ["busctl", "tree", "org.bluez", "/org/bluez"]:
            return CompletedProcess(argv, 1, stdout="", stderr="bad object path\n")
        if argv == ["busctl", "tree", "org.bluez"]:
            return CompletedProcess(
                argv,
                0,
                stdout="└─ /org/bluez/hci0\n   ├─ /org/bluez/hci0/dev_AA_BB\n",
                stderr="",
            )
        if argv[:2] == ["busctl", "introspect"]:
            return CompletedProcess(
                argv,
                0,
                stdout=".ServicesResolved  property  b  true\n",
                stderr="",
            )
        raise AssertionError(argv)

    with patch.object(bluez, "run_command", side_effect=fake_run):
        with patch.object(
            bluez.BleakScanner,
            "find_device_by_address",
            new=AsyncMock(return_value=None),
        ):
            with patch("bosch_ble.bluez.shutil.which", return_value="/usr/bin/busctl"):
                with patch("sys.argv", ["bosch-ble-bluez-preflight", "AA:BB"]):
                    bluez.preflight_cli()

    output = capsys.readouterr().out
    assert "ServicesResolved: yes" in output
    assert ["busctl", "tree", "org.bluez", "/org/bluez"] in calls
    assert ["busctl", "tree", "org.bluez"] in calls


def test_bluez_preflight_cli_reports_absent_device(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_run(argv: list[str], timeout: float = 0.0) -> CompletedProcess[str]:
        if argv[:2] == ["bluetoothctl", "info"]:
            return CompletedProcess(argv, 1, stdout="Device AA:BB not available\n", stderr="")
        raise AssertionError(argv)

    with patch.object(bluez, "run_command", side_effect=fake_run):
        with patch.object(
            bluez.BleakScanner,
            "find_device_by_address",
            new=AsyncMock(return_value=None),
        ):
            with patch("bosch_ble.bluez.shutil.which", return_value=None):
                with patch("sys.argv", ["bosch-ble-bluez-preflight", "AA:BB"]):
                    bluez.preflight_cli()

    output = capsys.readouterr().out
    assert "Visible: no" in output
    assert "== bluetoothctl info ==" in output


def test_bluez_wait_services_cli_shows_usage_without_address(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch("sys.argv", ["bosch-ble-bluez-wait-services"]):
        with pytest.raises(SystemExit) as excinfo:
            bluez.wait_services_cli()

    assert excinfo.value.code == 2
    assert "Usage: bosch-ble-bluez-wait-services <BLE_ADDRESS>" in capsys.readouterr().out


def test_bluez_wait_services_cli_exits_zero_when_services_resolve(
    capsys: pytest.CaptureFixture[str],
) -> None:
    states = iter(
        [
            bluez.BluezState(
                address="AA:BB",
                visible=True,
                device=None,
                name=None,
                paired=False,
                trusted=True,
                connected=True,
                services_resolved=False,
                bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
                busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
            ),
            bluez.BluezState(
                address="AA:BB",
                visible=True,
                device=None,
                name=None,
                paired=False,
                trusted=True,
                connected=True,
                services_resolved=True,
                bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
                busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
            ),
        ]
    )

    with patch.object(bluez, "read_device_state", side_effect=lambda address: next(states)):
        with patch("sys.argv", ["bosch-ble-bluez-wait-services", "AA:BB"]):
            bluez.wait_services_cli()

    output = capsys.readouterr().out
    assert "Waiting for services to resolve for AA:BB ..." in output
    assert "Services resolved for AA:BB." in output


def test_bluez_wait_services_cli_exits_nonzero_when_services_do_not_resolve(
    capsys: pytest.CaptureFixture[str],
) -> None:
    state = bluez.BluezState(
        address="AA:BB",
        visible=True,
        device=None,
        name=None,
        paired=False,
        trusted=True,
        connected=True,
        services_resolved=False,
        bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
        busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
    )

    with patch.object(bluez, "read_device_state", return_value=state):
        with patch.object(bluez.asyncio, "sleep", new=AsyncMock(return_value=None)):
            with patch("sys.argv", ["bosch-ble-bluez-wait-services", "AA:BB"]):
                with pytest.raises(SystemExit) as excinfo:
                    bluez.wait_services_cli()

    assert excinfo.value.code == 1
    output = capsys.readouterr()
    assert output.out == "Waiting for services to resolve for AA:BB ...\n"
    assert output.err == "Error: BlueZ connected to AA:BB but services did not resolve.\n"


def test_bluez_info_cli_shows_usage_without_address(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch("sys.argv", ["bosch-ble-bluez-info"]):
        with pytest.raises(SystemExit) as excinfo:
            bluez.info_cli()

    assert excinfo.value.code == 2
    assert "Usage: bosch-ble-bluez-info <BLE_ADDRESS>" in capsys.readouterr().out


def test_bluez_info_cli_runs_devices_info_and_busctl(
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], timeout: float = 0.0) -> CompletedProcess[str]:
        calls.append(argv)
        if argv[:2] == ["bluetoothctl", "devices"]:
            return CompletedProcess(argv, 0, stdout="Device AA:BB sensor\n", stderr="")
        if argv[:2] == ["bluetoothctl", "info"]:
            return CompletedProcess(argv, 0, stdout="Connected: no\n", stderr="")
        if argv[:2] == ["busctl", "tree"]:
            return CompletedProcess(
                argv,
                0,
                stdout="/org/bluez/hci1/dev_AA_BB\n",
                stderr="",
            )
        if argv[:2] == ["busctl", "introspect"]:
            return CompletedProcess(argv, 0, stdout="ServicesResolved false\n", stderr="")
        raise AssertionError(argv)

    with patch.object(bluez, "run_command", side_effect=fake_run):
        with patch("bosch_ble.bluez.shutil.which", return_value="/usr/bin/busctl"):
            with patch("sys.argv", ["bosch-ble-bluez-info", "AA:BB"]):
                bluez.info_cli()

    assert calls == [
        ["bluetoothctl", "devices"],
        ["bluetoothctl", "info", "AA:BB"],
        ["busctl", "tree", "org.bluez", "/org/bluez"],
        [
            "busctl",
            "introspect",
            "org.bluez",
            "/org/bluez/hci1/dev_AA_BB",
            "org.bluez.Device1",
        ],
    ]
    output = capsys.readouterr().out
    assert "== bluetoothctl devices ==" in output
    assert "Device AA:BB sensor" in output
    assert "== busctl introspect ==" in output


def test_bluez_connect_cli_runs_pair_trust_connect_sequence(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch.object(bluez, "assist_connection", new=AsyncMock()) as assist_connection:
        with patch("sys.argv", ["bosch-ble-bluez-connect", "AA:BB"]):
            bluez.connect_cli()

    assist_connection.assert_awaited_once_with("AA:BB", verbose=True)
    assert capsys.readouterr().out == ""


def test_bluez_connect_cli_exits_nonzero_when_connect_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch.object(
        bluez,
        "assist_connection",
        new=AsyncMock(side_effect=RuntimeError("BlueZ connect failed for AA:BB: Failed")),
    ):
        with patch("sys.argv", ["bosch-ble-bluez-connect", "AA:BB"]):
            with pytest.raises(SystemExit) as excinfo:
                bluez.connect_cli()

    assert excinfo.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "Error: BlueZ connect failed for AA:BB: Failed\n"


def test_list_busy_bluetooth_processes_filters_current_process() -> None:
    process_table = CompletedProcess(
        ["ps"],
        0,
        stdout=(
            "100 /usr/bin/python current-script.py\n"
            "101 uv run bosch-ble-handshake AA:BB\n"
            "102 bluetoothctl scan on\n"
            "103 something harmless\n"
        ),
        stderr="",
    )

    with patch.object(bluez, "run_command", return_value=process_table):
        busy = bluez.list_busy_bluetooth_processes(current_pid=100)

    assert busy == [
        "101 uv run bosch-ble-handshake AA:BB",
        "102 bluetoothctl scan on",
    ]


def test_list_busy_bluetooth_processes_ignores_remote_ssh_wrappers() -> None:
    process_table = CompletedProcess(
        ["ps"],
        0,
        stdout=(
            "100 ssh m710qa.local 'uv run bosch-ble-handshake AA:BB'\n"
            "101 uv run bosch-ble-dashboard AA:BB\n"
        ),
        stderr="",
    )

    with patch.object(bluez, "run_command", return_value=process_table):
        busy = bluez.list_busy_bluetooth_processes(current_pid=999)

    assert busy == ["101 uv run bosch-ble-dashboard AA:BB"]


def test_list_busy_bluetooth_processes_ignores_current_parent_chain() -> None:
    process_table = CompletedProcess(
        ["ps"],
        0,
        stdout=(
            "200 1 timeout 20s env PYTHONUNBUFFERED=1 uv run bosch-ble-handshake AA:BB\n"
            "201 200 uv run bosch-ble-handshake AA:BB\n"
            "202 201 /usr/bin/python bosch-ble-handshake AA:BB\n"
            "203 1 bluetoothctl connect AA:BB\n"
        ),
        stderr="",
    )

    with patch.object(bluez, "run_command", return_value=process_table):
        busy = bluez.list_busy_bluetooth_processes(current_pid=202)

    assert busy == ["203 bluetoothctl connect AA:BB"]


def test_list_busy_bluetooth_processes_ignores_passive_capture_viewers() -> None:
    process_table = CompletedProcess(
        ["ps"],
        0,
        stdout=(
            "100 /usr/bin/python current-script.py\n"
            "101 wireshark captures/session.pcapng\n"
            "102 tshark -r captures/session.pcapng\n"
            "103 btmon\n"
            "104 uv run bosch-ble-dashboard AA:BB\n"
        ),
        stderr="",
    )

    with patch.object(bluez, "run_command", return_value=process_table):
        busy = bluez.list_busy_bluetooth_processes(current_pid=100)

    assert busy == ["104 uv run bosch-ble-dashboard AA:BB"]


def test_assert_controller_ready_fails_when_discovering_or_busy() -> None:
    with pytest.raises(RuntimeError) as excinfo:
        bluez.assert_controller_ready(
            "AA:BB",
            discovering=True,
            busy_processes=["101 uv run bosch-ble-handshake AA:BB"],
        )

    assert str(excinfo.value) == (
        "Bluetooth controller is busy before connecting to AA:BB: "
        "controller discovery is already active; "
        "other Bluetooth tools are still running (101 uv run bosch-ble-handshake AA:BB)"
    )


def test_resolve_device_logs_controller_state_before_scan(
    capsys: pytest.CaptureFixture[str],
) -> None:
    state = bluez.BluezState(
        address="AA:BB",
        visible=True,
        device=None,
        name="sensor",
        paired=False,
        trusted=False,
        connected=False,
        services_resolved=None,
        bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
        busctl=None,
    )

    async def run() -> None:
        with patch.object(dump_gatt.bluez, "controller_discovering_state", return_value=False):
            with patch.object(dump_gatt.bluez, "assert_controller_ready") as assert_ready:
                with patch.object(dump_gatt.bluez, "preflight_device", new=AsyncMock(return_value=state)):
                    result = await dump_gatt.resolve_device("AA:BB")

        assert result is state
        assert_ready.assert_called_once_with("AA:BB", discovering=False)

    asyncio.run(run())

    output = capsys.readouterr().out
    assert "ControllerDiscovering: no" in output
