#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import uuid4

from bleak import BleakScanner
from dbus_fast import DBusError, Variant
from dbus_fast.annotations import DBusObjectPath, DBusSignature, DBusStr, DBusUInt16, DBusUInt32
from dbus_fast.aio import MessageBus
from dbus_fast.constants import BusType
from dbus_fast.service import ServiceInterface, method

DEFAULT_SCAN_TIMEOUT = 5.0
DEFAULT_WAIT_TIMEOUT = 8.0
DEFAULT_WAIT_INTERVAL = 1.0
BLUEZ_SERVICE = "org.bluez"
BLUEZ_ROOT_PATH = "/org/bluez"
BLUEZ_AGENT_INTERFACE = "org.bluez.Agent1"
BLUEZ_AGENT_MANAGER_INTERFACE = "org.bluez.AgentManager1"
BLUEZ_DEVICE_INTERFACE = "org.bluez.Device1"
DBUS_PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
BLUEZ_AGENT_CAPABILITY = "KeyboardDisplay"
BLUEZ_AGENT_BASE_PATH = "/org/bosch_ble"
BLUEZ_REJECTED_ERROR = "org.bluez.Error.Rejected"
DBusEmpty = Annotated[None, DBusSignature("")]
BUSY_PROCESS_PATTERNS = (
    "bosch-ble-handshake",
    "bosch-ble-dashboard",
    "bosch-ble-dump-gatt",
    "bosch-ble-log-chars",
    "bosch-ble-probe",
    "bluetoothctl scan",
    "bluetoothctl connect",
    "bluetoothctl pair",
    "bluetoothctl trust",
)


def log_agent_event(message: str) -> None:
    path = os.environ.get("BOSCH_BLE_AGENT_LOG")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"{message}\n")
    except OSError:
        pass


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


async def run_command_async(
    argv: list[str],
    timeout: float = 15.0,
) -> subprocess.CompletedProcess[str]:
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise subprocess.TimeoutExpired(argv, timeout) from exc
    return subprocess.CompletedProcess(
        argv,
        process.returncode,
        stdout=stdout.decode(),
        stderr=stderr.decode(),
    )


def print_section(title: str, result: subprocess.CompletedProcess[str]) -> None:
    print(f"== {title} ==")
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n")


def device_object_suffix(address: str) -> str:
    return f"dev_{address.upper().replace(':', '_')}"


def busctl_available() -> bool:
    return shutil.which("busctl") is not None


def find_device_object_path(address: str) -> str | None:
    if not busctl_available():
        return None

    tree = run_command(["busctl", "tree", "org.bluez", BLUEZ_ROOT_PATH])
    if tree.returncode != 0:
        tree = run_command(["busctl", "tree", "org.bluez"])
        if tree.returncode != 0:
            return None

    suffix = device_object_suffix(address)
    for line in tree.stdout.splitlines():
        marker = line.find("/org/bluez")
        if marker < 0:
            continue
        object_path = line[marker:].strip()
        if object_path.endswith(f"/{suffix}"):
            return object_path

    return None


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
        parts = [part.strip().lstrip(".").rstrip(":").lower() for part in normalized.split()]
        if key_lower in parts:
            key_index = parts.index(key_lower)
            for part in reversed(parts[key_index + 1 :]):
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
    device_path = find_device_object_path(address)
    if device_path is not None:
        busctl = run_command(
            [
                "busctl",
                "introspect",
                "org.bluez",
                device_path,
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


def controller_show() -> subprocess.CompletedProcess[str]:
    try:
        return run_command(["bluetoothctl", "show"])
    except FileNotFoundError:
        return subprocess.CompletedProcess(["bluetoothctl", "show"], 127, stdout="", stderr="")


def controller_discovering_state(show_result: subprocess.CompletedProcess[str] | None = None) -> bool | None:
    if show_result is None:
        show_result = controller_show()
    return parse_flag(f"{show_result.stdout}\n{show_result.stderr}", "Discovering")


def list_busy_bluetooth_processes(current_pid: int | None = None) -> list[str]:
    if current_pid is None:
        current_pid = os.getpid()

    result = run_command(["ps", "-eo", "pid=,ppid=,args="])
    if result.returncode != 0:
        return []

    process_rows: dict[int, tuple[int | None, str, str]] = {}
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        ppid: int | None = None
        args_index = 1
        if len(parts) == 3:
            try:
                ppid = int(parts[1])
                args_index = 2
            except ValueError:
                ppid = None
        if args_index == 1:
            args = " ".join(parts[1:])
        else:
            args = parts[args_index]
        process_rows[pid] = (ppid, args, f"{pid} {args}")

    ignored_pids = {current_pid}
    parent_pid = process_rows.get(current_pid, (os.getppid(), "", ""))[0]
    while parent_pid is not None and parent_pid > 1 and parent_pid not in ignored_pids:
        ignored_pids.add(parent_pid)
        parent_pid = process_rows.get(parent_pid, (None, "", ""))[0]

    busy: list[str] = []
    for pid, (_ppid, args, display_line) in process_rows.items():
        if pid in ignored_pids:
            continue
        if args.startswith("ssh "):
            continue
        if any(pattern in args for pattern in BUSY_PROCESS_PATTERNS):
            busy.append(display_line)
    return busy


def assert_controller_ready(
    address: str,
    *,
    discovering: bool | None = None,
    busy_processes: list[str] | None = None,
) -> None:
    if discovering is None:
        discovering = controller_discovering_state()
    if busy_processes is None:
        busy_processes = list_busy_bluetooth_processes()

    problems: list[str] = []
    if discovering is True:
        problems.append("controller discovery is already active")
    if busy_processes:
        joined = "; ".join(busy_processes[:3])
        if len(busy_processes) > 3:
            joined += "; ..."
        problems.append(f"other Bluetooth tools are still running ({joined})")
    if problems:
        raise RuntimeError(
            f"Bluetooth controller is busy before connecting to {address}: {'; '.join(problems)}"
        )


class AutoConfirmBluezAgent(ServiceInterface):
    def __init__(self, address: str) -> None:
        super().__init__(BLUEZ_AGENT_INTERFACE)
        self.address = address.upper()
        self.device_suffix = device_object_suffix(address)

    def _authorize_device(self, device: str) -> None:
        if device.endswith(self.device_suffix):
            log_agent_event(f"authorize ok {device}")
            return
        log_agent_event(f"authorize reject {device}")
        raise DBusError(BLUEZ_REJECTED_ERROR, f"Refusing pairing request for unexpected device {device}")

    @method()
    def Release(self) -> DBusEmpty:
        log_agent_event("Release")
        return None

    @method()
    def RequestPinCode(self, device: DBusObjectPath) -> DBusStr:
        self._authorize_device(device)
        log_agent_event(f"RequestPinCode {device}")
        raise DBusError(BLUEZ_REJECTED_ERROR, "PIN code entry is not supported")

    @method()
    def DisplayPinCode(self, device: DBusObjectPath, pincode: DBusStr) -> DBusEmpty:
        self._authorize_device(device)
        log_agent_event(f"DisplayPinCode {device} {pincode}")
        return None

    @method()
    def RequestPasskey(self, device: DBusObjectPath) -> DBusUInt32:
        self._authorize_device(device)
        log_agent_event(f"RequestPasskey {device}")
        raise DBusError(BLUEZ_REJECTED_ERROR, "Passkey entry is not supported")

    @method()
    def DisplayPasskey(
        self,
        device: DBusObjectPath,
        passkey: DBusUInt32,
        entered: DBusUInt16,
    ) -> DBusEmpty:
        self._authorize_device(device)
        log_agent_event(f"DisplayPasskey {device} {passkey:06d} entered={entered}")
        return None

    @method()
    def RequestConfirmation(self, device: DBusObjectPath, passkey: DBusUInt32) -> DBusEmpty:
        self._authorize_device(device)
        log_agent_event(f"RequestConfirmation {device} {passkey:06d}")
        return None

    @method()
    def RequestAuthorization(self, device: DBusObjectPath) -> DBusEmpty:
        self._authorize_device(device)
        log_agent_event(f"RequestAuthorization {device}")
        return None

    @method()
    def AuthorizeService(self, device: DBusObjectPath, uuid: DBusStr) -> DBusEmpty:
        self._authorize_device(device)
        log_agent_event(f"AuthorizeService {device} {uuid}")
        return None

    @method()
    def Cancel(self) -> DBusEmpty:
        log_agent_event("Cancel")
        return None


@asynccontextmanager
async def pairing_agent(address: str):
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    path = f"{BLUEZ_AGENT_BASE_PATH}/{uuid4().hex}"
    agent = AutoConfirmBluezAgent(address)
    bus.export(path, agent)
    introspection = await bus.introspect(BLUEZ_SERVICE, BLUEZ_ROOT_PATH)
    proxy = bus.get_proxy_object(BLUEZ_SERVICE, BLUEZ_ROOT_PATH, introspection)
    manager = proxy.get_interface(BLUEZ_AGENT_MANAGER_INTERFACE)
    log_agent_event(f"register {path} capability={BLUEZ_AGENT_CAPABILITY} address={address}")
    await manager.call_register_agent(path, BLUEZ_AGENT_CAPABILITY)
    try:
        await manager.call_request_default_agent(path)
        try:
            yield
        finally:
            try:
                log_agent_event(f"unregister {path}")
                await manager.call_unregister_agent(path)
            except Exception:
                pass
    finally:
        bus.unexport(path, agent)
        bus.disconnect()


async def bluez_pair_device(address: str) -> subprocess.CompletedProcess[str]:
    device_path = find_device_object_path(address)
    if device_path is None:
        return subprocess.CompletedProcess(
            ["bluez", "pair", address],
            1,
            stdout="",
            stderr=f"Device {address} not available\n",
        )

    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    try:
        introspection = await bus.introspect(BLUEZ_SERVICE, device_path)
        proxy = bus.get_proxy_object(BLUEZ_SERVICE, device_path, introspection)
        device = proxy.get_interface(BLUEZ_DEVICE_INTERFACE)
        await device.call_pair()
    except Exception as exc:
        return subprocess.CompletedProcess(
            ["bluez", "pair", address],
            1,
            stdout="",
            stderr=f"{format_cli_error(exc)}\n",
        )
    finally:
        bus.disconnect()

    return subprocess.CompletedProcess(["bluez", "pair", address], 0, stdout="", stderr="")


async def bluez_set_trusted(address: str, trusted: bool = True) -> subprocess.CompletedProcess[str]:
    device_path = find_device_object_path(address)
    if device_path is None:
        return subprocess.CompletedProcess(
            ["bluez", "trust", address],
            1,
            stdout="",
            stderr=f"Device {address} not available\n",
        )

    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    try:
        introspection = await bus.introspect(BLUEZ_SERVICE, device_path)
        proxy = bus.get_proxy_object(BLUEZ_SERVICE, device_path, introspection)
        props = proxy.get_interface(DBUS_PROPERTIES_INTERFACE)
        await props.call_set(BLUEZ_DEVICE_INTERFACE, "Trusted", Variant("b", trusted))
    except Exception as exc:
        return subprocess.CompletedProcess(
            ["bluez", "trust", address],
            1,
            stdout="",
            stderr=f"{format_cli_error(exc)}\n",
        )
    finally:
        bus.disconnect()

    return subprocess.CompletedProcess(["bluez", "trust", address], 0, stdout="", stderr="")


async def assist_connection(address: str, verbose: bool = False) -> BluezState:
    info_result = await run_command_async(["bluetoothctl", "info", address])
    info_state = build_state(address, info_result, None)
    steps = [("bluetoothctl info", ["bluetoothctl", "info", address], info_result)]
    if info_state.paired is not True:
        steps.append(("bluez pair", ["bluez", "pair", address], None))
    if info_state.trusted is not True:
        steps.append(("bluez trust", ["bluez", "trust", address], None))
    steps.append(("bluetoothctl connect", ["bluetoothctl", "connect", address], None))

    connect_result: subprocess.CompletedProcess[str] | None = None
    async with pairing_agent(address):
        for title, argv, result in steps:
            if result is None:
                if argv[:2] == ["bluez", "pair"]:
                    result = await bluez_pair_device(address)
                elif argv[:2] == ["bluez", "trust"]:
                    result = await bluez_set_trusted(address)
                else:
                    result = await run_command_async(argv)
            if verbose:
                print_section(title, result)
            if argv[:2] == ["bluez", "pair"] and result.returncode != 0:
                state = await asyncio.to_thread(read_device_state, address)
                if state.paired is not True:
                    raise RuntimeError(f"BlueZ pair failed for {address}: {summarize_failure(result)}")
            if argv[:2] == ["bluez", "trust"] and result.returncode != 0:
                state = await asyncio.to_thread(read_device_state, address)
                if state.trusted is not True:
                    raise RuntimeError(f"BlueZ trust failed for {address}: {summarize_failure(result)}")
            if argv[:2] == ["bluetoothctl", "connect"]:
                connect_result = result

    state = await asyncio.to_thread(read_device_state, address)
    if verbose:
        print_section("bluetoothctl info", state.bluetoothctl)
        if state.busctl is not None:
            print_section("busctl introspect", state.busctl)

    if connect_result is not None and connect_result.returncode != 0 and state.connected is not True:
        raise RuntimeError(f"BlueZ connect failed for {address}: {summarize_failure(connect_result)}")
    if state.connected is False:
        raise RuntimeError(f"BlueZ reports {address} is not connected after connect attempt.")
    return state


async def wait_for_services(
    address: str,
    timeout: float = DEFAULT_WAIT_TIMEOUT,
    interval: float = DEFAULT_WAIT_INTERVAL,
) -> BluezState:
    initial_state = read_device_state(address)
    if not busctl_available() and initial_state.services_resolved is None:
        return initial_state

    try:
        return await wait_for_state(
            address,
            connected=True,
            services_resolved=True,
            timeout=timeout,
            interval=interval,
        )
    except RuntimeError:
        last_state = read_device_state(address)
        if last_state.connected is True:
            raise RuntimeError(f"BlueZ connected to {address} but services did not resolve.")
        if last_state.connected is False:
            raise RuntimeError(f"BlueZ could not keep {address} connected long enough to resolve services.")
        raise RuntimeError(f"BlueZ did not report service resolution for {address}.")


async def wait_for_state(
    address: str,
    *,
    paired: bool | None = None,
    connected: bool | None = None,
    services_resolved: bool | None = None,
    timeout: float = DEFAULT_WAIT_TIMEOUT,
    interval: float = DEFAULT_WAIT_INTERVAL,
) -> BluezState:
    last_state = read_device_state(address)
    target_services_resolved = services_resolved
    if (
        target_services_resolved is not None
        and not busctl_available()
        and last_state.services_resolved is None
    ):
        target_services_resolved = None

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    def matches(state: BluezState) -> bool:
        if paired is not None and state.paired is not paired:
            return False
        if connected is not None and state.connected is not connected:
            return False
        if (
            target_services_resolved is not None
            and state.services_resolved is not target_services_resolved
        ):
            return False
        return True

    while True:
        if matches(last_state):
            return last_state
        if loop.time() >= deadline:
            break
        await asyncio.sleep(interval)
        last_state = read_device_state(address)

    expected_flags: list[str] = []
    if paired is not None:
        expected_flags.append(f"paired={paired}")
    if connected is not None:
        expected_flags.append(f"connected={connected}")
    if target_services_resolved is not None:
        expected_flags.append(f"services_resolved={target_services_resolved}")
    expected = ", ".join(expected_flags) if expected_flags else "requested state"
    raise RuntimeError(f"BlueZ did not reach {expected} for {address}.")


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
        asyncio.run(assist_connection(sys.argv[1], verbose=True))
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
