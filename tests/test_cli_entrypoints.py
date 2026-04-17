from __future__ import annotations

from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from bosch_ble import bluez, dump_gatt, log_chars


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
        [
            "busctl",
            "introspect",
            "org.bluez",
            "/org/bluez/hci0/dev_AA_BB",
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
    calls: list[list[str]] = []

    def fake_run(argv: list[str], timeout: float = 0.0) -> CompletedProcess[str]:
        calls.append(argv)
        return CompletedProcess(argv, 0, stdout="ok\n", stderr="")

    with patch.object(bluez, "run_command", side_effect=fake_run):
        with patch("sys.argv", ["bosch-ble-bluez-connect", "AA:BB"]):
            bluez.connect_cli()

    assert calls == [
        ["bluetoothctl", "info", "AA:BB"],
        ["bluetoothctl", "pair", "AA:BB"],
        ["bluetoothctl", "trust", "AA:BB"],
        ["bluetoothctl", "connect", "AA:BB"],
        ["bluetoothctl", "info", "AA:BB"],
    ]
    output = capsys.readouterr().out
    assert "== bluetoothctl connect ==" in output
    assert "ok" in output


def test_bluez_connect_cli_exits_nonzero_when_connect_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_run(argv: list[str], timeout: float = 0.0) -> CompletedProcess[str]:
        if argv[:2] == ["bluetoothctl", "connect"]:
            return CompletedProcess(argv, 1, stdout="", stderr="Failed\n")
        return CompletedProcess(argv, 0, stdout="ok\n", stderr="")

    with patch.object(bluez, "run_command", side_effect=fake_run):
        with patch("sys.argv", ["bosch-ble-bluez-connect", "AA:BB"]):
            with pytest.raises(SystemExit) as excinfo:
                bluez.connect_cli()

    assert excinfo.value.code == 1
    output = capsys.readouterr().out
    assert "== bluetoothctl connect ==" in output
    assert "Failed" in output
