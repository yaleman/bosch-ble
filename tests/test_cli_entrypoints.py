from __future__ import annotations

from unittest.mock import patch

import pytest

from bosch_ble import dump_gatt, log_chars


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


def test_dump_gatt_main_resolves_device_before_connecting(capsys: pytest.CaptureFixture[str]) -> None:
    class FakeClient:
        def __init__(self, address_or_ble_device, timeout: float = 20.0) -> None:
            self.address_or_ble_device = address_or_ble_device
            self.timeout = timeout
            self.is_connected = True
            self.services = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    fake_device = object()

    async def run() -> None:
        with patch.object(
            dump_gatt.BleakScanner,
            "find_device_by_address",
            side_effect=lambda address, timeout=10.0: fake_device,
        ) as find_device:
            with patch.object(dump_gatt, "BleakClient", FakeClient):
                await dump_gatt.main("AA:BB")

        find_device.assert_called_once_with("AA:BB", timeout=10.0)

    import asyncio

    asyncio.run(run())
    assert "Connecting to AA:BB ..." in capsys.readouterr().out


def test_dump_gatt_main_errors_cleanly_when_scan_cannot_find_device() -> None:
    async def run() -> None:
        with patch.object(
            dump_gatt.BleakScanner,
            "find_device_by_address",
            side_effect=lambda address, timeout=10.0: None,
        ):
            with pytest.raises(RuntimeError) as excinfo:
                await dump_gatt.main("AA:BB")

        assert str(excinfo.value) == "Device with address AA:BB was not found."

    import asyncio

    asyncio.run(run())


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
        with patch.object(
            dump_gatt.BleakScanner,
            "find_device_by_address",
            side_effect=lambda address, timeout=10.0: object(),
        ) as find_device:
            with patch.object(dump_gatt, "BleakClient", FakeClient):
                await dump_gatt.main("AA:BB")

        assert find_device.call_count == 2

    import asyncio

    asyncio.run(run())
    output = capsys.readouterr().out
    assert "Connecting to AA:BB ..." in output
    assert "Retrying service discovery for AA:BB ..." in output


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
        with patch.object(
            dump_gatt.BleakScanner,
            "find_device_by_address",
            side_effect=lambda address, timeout=10.0: object(),
        ) as find_device:
            with patch.object(dump_gatt, "BleakClient", FakeClient):
                await dump_gatt.main("AA:BB")

        assert find_device.call_count == 3

    import asyncio

    asyncio.run(run())
    output = capsys.readouterr().out
    assert "Retrying service discovery for AA:BB ..." in output
    assert "Retrying connection setup for AA:BB ..." in output


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
