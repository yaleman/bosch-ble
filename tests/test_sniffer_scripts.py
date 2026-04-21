from __future__ import annotations

from pathlib import Path
import tomllib


def test_sniffer_scripts_exist() -> None:
    for name in (
        "sniff-start",
        "sniff-stop",
        "sniff-copy",
        "bluetoothd-debug-enable",
        "bluetoothd-debug-disable",
        "bluetoothd-debug-tail",
    ):
        path = Path("scripts") / name
        assert path.is_file(), f"missing script: {path}"


def test_mise_exposes_sniffer_scripts() -> None:
    config = tomllib.loads(Path("mise.toml").read_text())
    tasks = config["tasks"]

    assert tasks["sniff-start"]["run"] == "./scripts/sniff-start"
    assert tasks["sniff-stop"]["run"] == "./scripts/sniff-stop"
    assert tasks["sniff-copy"]["run"] == "./scripts/sniff-copy"
    assert tasks["bluetoothd-debug-enable"]["run"] == "./scripts/bluetoothd-debug-enable"
    assert tasks["bluetoothd-debug-disable"]["run"] == "./scripts/bluetoothd-debug-disable"
    assert tasks["bluetoothd-debug-tail"]["run"] == "./scripts/bluetoothd-debug-tail"


def test_sniffer_scripts_use_remote_host_environment_variable() -> None:
    for name in (
        "sniff-start",
        "sniff-stop",
        "sniff-copy",
        "bluetoothd-debug-enable",
        "bluetoothd-debug-disable",
        "bluetoothd-debug-tail",
    ):
        content = (Path("scripts") / name).read_text()
        assert "REMOTE_HOST" in content


def test_bluetoothd_debug_scripts_manage_expected_dropin() -> None:
    enable = (Path("scripts") / "bluetoothd-debug-enable").read_text()
    disable = (Path("scripts") / "bluetoothd-debug-disable").read_text()
    tail = (Path("scripts") / "bluetoothd-debug-tail").read_text()

    assert "/etc/systemd/system/bluetooth.service.d/debug.conf" in enable
    assert "ExecStart=/usr/libexec/bluetooth/bluetoothd -d" in enable
    assert "systemctl daemon-reload" in enable
    assert "systemctl restart bluetooth" in enable

    assert "/etc/systemd/system/bluetooth.service.d/debug.conf" in disable
    assert "systemctl daemon-reload" in disable
    assert "systemctl restart bluetooth" in disable

    assert "journalctl -u bluetooth -f" in tail
