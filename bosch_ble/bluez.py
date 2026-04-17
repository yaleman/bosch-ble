#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys


def run_command(argv: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def print_section(title: str, result: subprocess.CompletedProcess[str]) -> None:
    print(f"== {title} ==")
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n")


def device_object_path(address: str) -> str:
    return f"/org/bluez/hci0/dev_{address.upper().replace(':', '_')}"


def info_cli() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <BLE_ADDRESS>")
        raise SystemExit(2)

    address = sys.argv[1]
    devices = run_command(["bluetoothctl", "devices"])
    print_section("bluetoothctl devices", devices)

    info = run_command(["bluetoothctl", "info", address])
    print_section("bluetoothctl info", info)

    if shutil.which("busctl") is not None:
        introspect = run_command(
            [
                "busctl",
                "introspect",
                "org.bluez",
                device_object_path(address),
                "org.bluez.Device1",
            ]
        )
        print_section("busctl introspect", introspect)


def connect_cli() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <BLE_ADDRESS>")
        raise SystemExit(2)

    address = sys.argv[1]
    steps = [
        ("bluetoothctl info", ["bluetoothctl", "info", address]),
        ("bluetoothctl pair", ["bluetoothctl", "pair", address]),
        ("bluetoothctl trust", ["bluetoothctl", "trust", address]),
        ("bluetoothctl connect", ["bluetoothctl", "connect", address]),
        ("bluetoothctl info", ["bluetoothctl", "info", address]),
    ]

    connect_code = 0
    for title, argv in steps:
        result = run_command(argv)
        print_section(title, result)
        if argv[:2] == ["bluetoothctl", "connect"]:
            connect_code = result.returncode

    if connect_code != 0:
        raise SystemExit(1)
