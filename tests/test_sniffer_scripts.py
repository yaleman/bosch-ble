from __future__ import annotations

import os
from pathlib import Path
import subprocess
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
    assert "BatchMode=yes" in enable
    assert "sudo -n bash -s" in enable
    assert "systemctl daemon-reload" in enable
    assert "systemctl restart bluetooth" in enable
    assert "systemctl is-active bluetooth.service" in enable

    assert "/etc/systemd/system/bluetooth.service.d/debug.conf" in disable
    assert "BatchMode=yes" in disable
    assert "sudo -n bash -s" in disable
    assert "systemctl daemon-reload" in disable
    assert "systemctl restart bluetooth" in disable
    assert "systemctl is-active bluetooth.service" in disable

    assert "BatchMode=yes" in tail
    assert "sudo -n journalctl -u bluetooth -f" in tail
    assert "journalctl -u bluetooth -f" in tail


def test_bluetoothd_debug_enable_runs_noninteractive_single_ssh_session(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "ssh.log"
    stdin_path = tmp_path / "ssh.stdin"
    fake_ssh = bin_dir / "ssh"
    fake_ssh.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"printf '%s\\n' \"$@\" > {log_path}",
                f"cat > {stdin_path}",
            ]
        )
        + "\n"
    )
    fake_ssh.chmod(0o755)

    env = os.environ | {"PATH": f"{bin_dir}:{os.environ['PATH']}", "REMOTE_HOST": "bikebox"}
    result = subprocess.run(
        ["bash", "scripts/bluetoothd-debug-enable"],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert log_path.read_text().splitlines() == [
        "-o",
        "BatchMode=yes",
        "-o",
        "LogLevel=ERROR",
        "bikebox",
        "sudo",
        "-n",
        "bash",
        "-s",
    ]
    payload = stdin_path.read_text()
    assert "ExecStart=/usr/libexec/bluetooth/bluetoothd -d" in payload
    assert "systemctl daemon-reload" in payload
    assert "systemctl restart bluetooth" in payload
    assert "systemctl is-active bluetooth.service" in payload


def test_bluetoothd_debug_disable_runs_noninteractive_single_ssh_session(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "ssh.log"
    stdin_path = tmp_path / "ssh.stdin"
    fake_ssh = bin_dir / "ssh"
    fake_ssh.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"printf '%s\\n' \"$@\" > {log_path}",
                f"cat > {stdin_path}",
            ]
        )
        + "\n"
    )
    fake_ssh.chmod(0o755)

    env = os.environ | {"PATH": f"{bin_dir}:{os.environ['PATH']}", "REMOTE_HOST": "bikebox"}
    result = subprocess.run(
        ["bash", "scripts/bluetoothd-debug-disable"],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert log_path.read_text().splitlines() == [
        "-o",
        "BatchMode=yes",
        "-o",
        "LogLevel=ERROR",
        "bikebox",
        "sudo",
        "-n",
        "bash",
        "-s",
    ]
    payload = stdin_path.read_text()
    assert 'dropin_file="/etc/systemd/system/bluetooth.service.d/debug.conf"' in payload
    assert 'rm -f "${dropin_file}"' in payload
    assert "systemctl daemon-reload" in payload
    assert "systemctl restart bluetooth" in payload
    assert "systemctl is-active bluetooth.service" in payload
