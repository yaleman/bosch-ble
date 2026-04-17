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
