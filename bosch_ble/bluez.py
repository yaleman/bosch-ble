#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

from bleak import BleakScanner

DEFAULT_SCAN_TIMEOUT = 5.0
DEFAULT_WAIT_TIMEOUT = 8.0
DEFAULT_WAIT_INTERVAL = 1.0


@dataclass(slots=True)
class BluezState:
    address: str
    visible: bool
    device: Any | None
    name: str | None
    paired: bool | None
    trusted: bool | None
    connected: bool | None
    services_resolved: bool | None
    bluetoothctl: subprocess.CompletedProcess[str]
    busctl: subprocess.CompletedProcess[str] | None


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


def format_cli_error(exc: Exception) -> str:
    return str(exc) or type(exc).__name__


def format_flag(value: bool | None) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def parse_flag(text: str, key: str) -> bool | None:
    key_lower = key.lower()
    for line in text.splitlines():
        normalized = line.strip()
        if not normalized:
            continue
        lower = normalized.lower()
        if lower.startswith(f"{key_lower}:"):
            value = normalized.split(":", 1)[1].strip().lower()
            if value in {"yes", "true"}:
                return True
            if value in {"no", "false"}:
                return False
        parts = normalized.split()
        if parts and parts[0].lower() == key_lower:
            for part in reversed(parts[1:]):
                value = part.strip().lower()
                if value in {"yes", "true"}:
                    return True
                if value in {"no", "false"}:
                    return False
    return None


def build_state(
    address: str,
    bluetoothctl: subprocess.CompletedProcess[str],
    busctl: subprocess.CompletedProcess[str] | None,
    *,
    device: Any | None = None,
    visible: bool | None = None,
) -> BluezState:
    if visible is None:
        visible = device is not None
    bluetoothctl_text = f"{bluetoothctl.stdout}\n{bluetoothctl.stderr}"
    busctl_text = ""
    if busctl is not None:
        busctl_text = f"{busctl.stdout}\n{busctl.stderr}"
    return BluezState(
        address=address,
        visible=visible,
        device=device,
        name=getattr(device, "name", None),
        paired=parse_flag(bluetoothctl_text, "Paired"),
        trusted=parse_flag(bluetoothctl_text, "Trusted"),
        connected=parse_flag(bluetoothctl_text, "Connected"),
        services_resolved=parse_flag(busctl_text, "ServicesResolved"),
        bluetoothctl=bluetoothctl,
        busctl=busctl,
    )


def read_device_state(
    address: str,
    *,
    device: Any | None = None,
    visible: bool | None = None,
) -> BluezState:
    bluetoothctl = run_command(["bluetoothctl", "info", address])
    busctl = None
    if shutil.which("busctl") is not None:
        busctl = run_command(
            [
                "busctl",
                "introspect",
                "org.bluez",
                device_object_path(address),
                "org.bluez.Device1",
            ]
        )
    return build_state(address, bluetoothctl, busctl, device=device, visible=visible)


async def preflight_device(address: str, scan_timeout: float = DEFAULT_SCAN_TIMEOUT) -> BluezState:
    device = await BleakScanner.find_device_by_address(address, timeout=scan_timeout)
    return read_device_state(address, device=device, visible=device is not None)


def print_preflight_summary(state: BluezState) -> None:
    print("== preflight ==")
    print(f"Address: {state.address}")
    print(f"Visible: {format_flag(state.visible)}")
    if state.name:
        print(f"Name: {state.name}")
    print(f"Paired: {format_flag(state.paired)}")
    print(f"Trusted: {format_flag(state.trusted)}")
    print(f"Connected: {format_flag(state.connected)}")
    print(f"ServicesResolved: {format_flag(state.services_resolved)}")


def print_preflight_report(state: BluezState) -> None:
    print_preflight_summary(state)
    print_section("bluetoothctl info", state.bluetoothctl)
    if state.busctl is not None:
        print_section("busctl introspect", state.busctl)


def summarize_failure(result: subprocess.CompletedProcess[str]) -> str:
    candidates = [
        line.strip()
        for line in [result.stderr, result.stdout]
        if line.strip()
    ]
    if candidates:
        return candidates[0].splitlines()[-1]
    return f"exit code {result.returncode}"


def assist_connection(address: str, verbose: bool = False) -> BluezState:
    steps = [
        ("bluetoothctl info", ["bluetoothctl", "info", address]),
        ("bluetoothctl pair", ["bluetoothctl", "pair", address]),
        ("bluetoothctl trust", ["bluetoothctl", "trust", address]),
        ("bluetoothctl connect", ["bluetoothctl", "connect", address]),
    ]

    connect_result: subprocess.CompletedProcess[str] | None = None
    for title, argv in steps:
        result = run_command(argv)
        if verbose:
            print_section(title, result)
        if argv[:2] == ["bluetoothctl", "connect"]:
            connect_result = result

    state = read_device_state(address)
    if verbose:
        print_section("bluetoothctl info", state.bluetoothctl)
        if state.busctl is not None:
            print_section("busctl introspect", state.busctl)

    if connect_result is not None and connect_result.returncode != 0:
        raise RuntimeError(f"BlueZ connect failed for {address}: {summarize_failure(connect_result)}")
    if state.connected is False:
        raise RuntimeError(f"BlueZ reports {address} is not connected after connect attempt.")
    return state


async def wait_for_services(
    address: str,
    timeout: float = DEFAULT_WAIT_TIMEOUT,
    interval: float = DEFAULT_WAIT_INTERVAL,
) -> BluezState:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    last_state = read_device_state(address)

    while True:
        if last_state.services_resolved is True:
            return last_state
        if loop.time() >= deadline:
            break
        await asyncio.sleep(interval)
        last_state = read_device_state(address)

    if last_state.connected is True:
        raise RuntimeError(f"BlueZ connected to {address} but services did not resolve.")
    if last_state.connected is False:
        raise RuntimeError(f"BlueZ could not keep {address} connected long enough to resolve services.")
    raise RuntimeError(f"BlueZ did not report service resolution for {address}.")


def info_cli() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <BLE_ADDRESS>")
        raise SystemExit(2)

    address = sys.argv[1]
    devices = run_command(["bluetoothctl", "devices"])
    print_section("bluetoothctl devices", devices)

    state = read_device_state(address)
    print_section("bluetoothctl info", state.bluetoothctl)
    if state.busctl is not None:
        print_section("busctl introspect", state.busctl)


def preflight_cli() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <BLE_ADDRESS>")
        raise SystemExit(2)

    try:
        state = asyncio.run(preflight_device(sys.argv[1]))
        print_preflight_report(state)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {format_cli_error(exc)}", file=sys.stderr)
        raise SystemExit(1)


def connect_cli() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <BLE_ADDRESS>")
        raise SystemExit(2)

    try:
        assist_connection(sys.argv[1], verbose=True)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {format_cli_error(exc)}", file=sys.stderr)
        raise SystemExit(1)


def wait_services_cli() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <BLE_ADDRESS>")
        raise SystemExit(2)

    address = sys.argv[1]
    print(f"Waiting for services to resolve for {address} ...")
    try:
        asyncio.run(wait_for_services(address))
        print(f"Services resolved for {address}.")
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {format_cli_error(exc)}", file=sys.stderr)
        raise SystemExit(1)
