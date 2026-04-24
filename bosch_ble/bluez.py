#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal
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
PHONE_LIKE_LE_CONNECTION_SYS_CONFIG = (
    "0017:2:1800",  # min interval 30 ms
    "0018:2:1800",  # max interval 30 ms
    "0019:2:0000",  # latency 0
    "001a:2:4800",  # supervision timeout 720 ms
)
PHONE_LIKE_LE_CONNECTION_UNITS = {
    "min_interval": 24,
    "max_interval": 24,
    "latency": 0,
    "timeout": 72,
}
BOSCH_PAIRING_MANUFACTURER_PAYLOAD = bytes.fromhex("01030001")


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
    pairing_advertisement: bool | None = None


@dataclass(slots=True)
class PairAttemptSummary:
    pair_backend: str
    privacy: str
    visible: bool
    name: str | None
    assist_error: str | None
    create_connection_seen: bool
    enhanced_connection_complete_seen: bool
    read_remote_features_seen: bool
    disconnect_reason: str | None
    att_seen: bool
    smp_seen: bool
    highest_stage: str
    trace_path: str


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


def normalize_address(address: str) -> str:
    return address.upper()


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
    pairing_advertisement: bool | None = None,
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
        pairing_advertisement=pairing_advertisement,
    )


def read_device_state(
    address: str,
    *,
    device: Any | None = None,
    visible: bool | None = None,
    pairing_advertisement: bool | None = None,
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
    return build_state(
        address,
        bluetoothctl,
        busctl,
        device=device,
        visible=visible,
        pairing_advertisement=pairing_advertisement,
    )


def is_bosch_pairing_advertisement(advertisement_data: Any | None) -> bool | None:
    if advertisement_data is None:
        return None
    manufacturer_data = getattr(advertisement_data, "manufacturer_data", None) or {}
    for payload in manufacturer_data.values():
        if bytes(payload) == BOSCH_PAIRING_MANUFACTURER_PAYLOAD:
            return True
    return False


async def scan_device_advertisement(
    address: str,
    timeout: float,
) -> tuple[Any | None, Any | None]:
    target_address = normalize_address(address)
    found_device: Any | None = None
    found_advertisement: Any | None = None
    pairing_seen = asyncio.Event()

    def detection_callback(device: Any, advertisement_data: Any) -> None:
        nonlocal found_device, found_advertisement
        device_address = getattr(device, "address", None)
        if not isinstance(device_address, str) or normalize_address(device_address) != target_address:
            return
        found_device = device
        found_advertisement = advertisement_data
        if is_bosch_pairing_advertisement(advertisement_data):
            pairing_seen.set()

    scanner = BleakScanner(detection_callback=detection_callback)
    await scanner.start()
    try:
        try:
            await asyncio.wait_for(pairing_seen.wait(), timeout=timeout)
        except TimeoutError:
            pass
    finally:
        await scanner.stop()

    return found_device, found_advertisement


async def preflight_device(address: str, scan_timeout: float = DEFAULT_SCAN_TIMEOUT) -> BluezState:
    device, advertisement_data = await scan_device_advertisement(address, scan_timeout)
    return read_device_state(
        address,
        device=device,
        visible=device is not None,
        pairing_advertisement=is_bosch_pairing_advertisement(advertisement_data),
    )


def print_preflight_summary(state: BluezState) -> None:
    print("== preflight ==")
    print(f"Address: {state.address}")
    print(f"Visible: {format_flag(state.visible)}")
    if state.pairing_advertisement is not None:
        print(f"PairingAdvertisement: {format_flag(state.pairing_advertisement)}")
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


def detect_trace_stage(trace_text: str) -> str:
    has_smp = "SMP" in trace_text or "Security Manager Protocol" in trace_text
    has_att = "ATT" in trace_text or "Attribute Protocol" in trace_text
    has_ll_control = any(
        marker in trace_text
        for marker in (
            "Control Opcode: LL_",
            "LL_VERSION_IND",
            "LL_FEATURE_REQ",
            "LL_FEATURE_RSP",
            "LL_LENGTH_REQ",
            "LL_LENGTH_RSP",
        )
    )
    has_remote_features = "LE Read Remote Used Features" in trace_text
    has_connection_complete = "LE Enhanced Connection Complete" in trace_text

    if has_smp:
        return "smp"
    if has_att:
        return "att"
    if has_ll_control:
        return "ll_control"
    if has_remote_features:
        return "remote_features"
    if has_connection_complete:
        return "connection_complete"
    return "pre_connection"


def summarize_btmon_trace(
    trace_text: str,
    *,
    pair_backend: str,
    privacy: str,
    visible: bool,
    name: str | None,
    assist_error: str | None,
    trace_path: str,
) -> PairAttemptSummary:
    disconnect_reason = None
    match = re.search(r"Reason:\s+([^\n]+)", trace_text)
    if match is not None:
        disconnect_reason = match.group(1).strip()

    return PairAttemptSummary(
        pair_backend=pair_backend,
        privacy=privacy,
        visible=visible,
        name=name,
        assist_error=assist_error,
        create_connection_seen="LE Create Connection" in trace_text,
        enhanced_connection_complete_seen="LE Enhanced Connection Complete" in trace_text,
        read_remote_features_seen="LE Read Remote Used Features" in trace_text,
        disconnect_reason=disconnect_reason,
        att_seen="ATT" in trace_text or "Attribute Protocol" in trace_text,
        smp_seen="SMP" in trace_text or "Security Manager Protocol" in trace_text,
        highest_stage=detect_trace_stage(trace_text),
        trace_path=trace_path,
    )


def print_pair_attempt_summary(summary: PairAttemptSummary) -> None:
    print(f"Backend: {summary.pair_backend}")
    print(f"Privacy: {summary.privacy}")
    print(f"Visible: {format_flag(summary.visible)}")
    if summary.name:
        print(f"Name: {summary.name}")
    print(f"HighestStage: {summary.highest_stage}")
    print(f"CreateConnection: {format_flag(summary.create_connection_seen)}")
    print(f"EnhancedConnectionComplete: {format_flag(summary.enhanced_connection_complete_seen)}")
    print(f"ReadRemoteFeatures: {format_flag(summary.read_remote_features_seen)}")
    print(f"ATT: {format_flag(summary.att_seen)}")
    print(f"SMP: {format_flag(summary.smp_seen)}")
    if summary.disconnect_reason:
        print(f"DisconnectReason: {summary.disconnect_reason}")
    if summary.assist_error:
        print(f"AssistError: {summary.assist_error}")
    print(f"Trace: {summary.trace_path}")


def is_transient_pair_failure(result: subprocess.CompletedProcess[str]) -> bool:
    text = "\n".join(part for part in (result.stderr, result.stdout) if part).lower()
    return any(
        marker in text
        for marker in (
            "page timeout",
            "connect failed",
            "connection failed to be established",
            "le-connection-abort-by-local",
        )
    )


def is_device_unavailable(result: subprocess.CompletedProcess[str]) -> bool:
    text = "\n".join(part for part in (result.stdout, result.stderr) if part).lower()
    return "not available" in text


def has_interactive_terminal() -> bool:
    return all(getattr(stream, "isatty", lambda: False)() for stream in (sys.stdin, sys.stdout, sys.stderr))


async def ensure_sudo_ready() -> None:
    if not has_interactive_terminal():
        return
    result = await asyncio.to_thread(
        subprocess.run,
        ["sudo", "-v"],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("sudo authentication failed for BlueZ setup.")


def assert_pairing_advertisement_ready(state: BluezState, address: str) -> None:
    if state.visible is not True:
        raise RuntimeError(f"{address} is not visible to BlueZ; wake the bike and retry.")
    if state.paired is True:
        return
    if state.pairing_advertisement is False:
        raise RuntimeError(f"{address} is visible but not in Bosch pairing advertisement mode.")


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


async def btmgmt_pair_device(address: str) -> subprocess.CompletedProcess[str]:
    return await run_command_async(
        ["sudo", "btmgmt", "pair", "-c", "4", "-t", "le-public", address],
        timeout=20.0,
    )


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


async def bluez_set_pairable(pairable: bool = True) -> subprocess.CompletedProcess[str]:
    value = "on" if pairable else "off"
    return await run_command_async(["bluetoothctl", "pairable", value])


async def bluez_set_power(powered: bool = True) -> subprocess.CompletedProcess[str]:
    value = "on" if powered else "off"
    return await run_command_async(["sudo", "btmgmt", "power", value])


async def bluez_set_privacy(privacy: bool = True) -> subprocess.CompletedProcess[str]:
    value = "on" if privacy else "off"
    return await run_command_async(["sudo", "btmgmt", "privacy", value])


async def bluez_set_bondable(bondable: bool = True) -> subprocess.CompletedProcess[str]:
    value = "on" if bondable else "off"
    return await run_command_async(["sudo", "btmgmt", "bondable", value])


async def bluez_prepare_phone_like_pairing_controller(*, privacy: bool = False) -> None:
    steps = [
        ("power off", lambda: bluez_set_power(False)),
        (
            "set-sysconfig",
            lambda: run_command_async(["sudo", "btmgmt", "set-sysconfig", "-v", *PHONE_LIKE_LE_CONNECTION_SYS_CONFIG]),
        ),
        ("privacy", lambda: bluez_set_privacy(privacy)),
        ("bondable", lambda: bluez_set_bondable(True)),
        ("power on", lambda: bluez_set_power(True)),
    ]

    for label, command_factory in steps:
        result = await command_factory()
        if result.returncode != 0:
            raise RuntimeError(f"BlueZ {label} failed: {summarize_failure(result)}")


async def refresh_visible_device(address: str) -> BluezState:
    return await preflight_device(address, scan_timeout=DEFAULT_SCAN_TIMEOUT)


async def bluez_load_connection_parameters(
    address: str,
    *,
    controller_index: int = 0,
    address_type: int = 1,
    min_interval: int = PHONE_LIKE_LE_CONNECTION_UNITS["min_interval"],
    max_interval: int = PHONE_LIKE_LE_CONNECTION_UNITS["max_interval"],
    latency: int = PHONE_LIKE_LE_CONNECTION_UNITS["latency"],
    timeout: int = PHONE_LIKE_LE_CONNECTION_UNITS["timeout"],
) -> subprocess.CompletedProcess[str]:
    return await run_command_async(
        [
            "sudo",
            "-n",
            sys.executable,
            "-m",
            "bosch_ble.mgmt",
            "load-conn-params",
            "--address",
            address,
            "--controller-index",
            str(controller_index),
            "--address-type",
            str(address_type),
            "--min-interval",
            str(min_interval),
            "--max-interval",
            str(max_interval),
            "--latency",
            str(latency),
            "--timeout",
            str(timeout),
        ],
        timeout=20.0,
    )


async def assist_connection(
    address: str,
    verbose: bool = False,
    *,
    pair_backend: Literal["dbus", "btmgmt"] = "dbus",
    privacy: bool = False,
) -> BluezState:
    info_result = await run_command_async(["bluetoothctl", "info", address])
    info_state = build_state(address, info_result, None)
    if is_device_unavailable(info_result):
        info_state = await preflight_device(address, scan_timeout=DEFAULT_SCAN_TIMEOUT)
        info_result = info_state.bluetoothctl
    connect_result: subprocess.CompletedProcess[str] | None = None
    async with pairing_agent(address):
        if verbose:
            print_section("bluetoothctl info", info_result)

        if info_state.paired is not True:
            await ensure_sudo_ready()
            last_pair_result: subprocess.CompletedProcess[str] | None = None
            for attempt in range(3):
                await bluez_prepare_phone_like_pairing_controller(privacy=privacy)

                pairable_result = await bluez_set_pairable(True)
                if verbose:
                    print_section("bluetoothctl pairable on", pairable_result)

                info_state = await refresh_visible_device(address)
                assert_pairing_advertisement_ready(info_state, address)
                if verbose:
                    print_section("post-prepare preflight", info_state.bluetoothctl)

                load_conn_params_result = await bluez_load_connection_parameters(address)
                if verbose:
                    print_section("load connection parameters", load_conn_params_result)
                if load_conn_params_result.returncode != 0:
                    raise RuntimeError(
                        f"BlueZ load-conn-params failed for {address}: {summarize_failure(load_conn_params_result)}"
                    )

                if pair_backend == "btmgmt":
                    pair_result = await btmgmt_pair_device(address)
                else:
                    pair_result = await bluez_pair_device(address)
                last_pair_result = pair_result
                if verbose:
                    print_section(f"{pair_backend} pair", pair_result)
                if pair_result.returncode == 0:
                    break

                state = await asyncio.to_thread(read_device_state, address)
                if state.paired is True:
                    break
                if attempt == 2 or not is_transient_pair_failure(pair_result):
                    raise RuntimeError(f"BlueZ pair failed for {address}: {summarize_failure(pair_result)}")
                await asyncio.sleep(1.0)

            if last_pair_result is None:
                raise RuntimeError(f"BlueZ pair failed for {address}: pair step was not executed")

        if info_state.trusted is not True:
            trust_result = await bluez_set_trusted(address)
            if verbose:
                print_section("bluez trust", trust_result)
            if trust_result.returncode != 0:
                state = await asyncio.to_thread(read_device_state, address)
                if state.trusted is not True:
                    raise RuntimeError(f"BlueZ trust failed for {address}: {summarize_failure(trust_result)}")

        connect_result = await run_command_async(["bluetoothctl", "connect", address])
        if verbose:
            print_section("bluetoothctl connect", connect_result)

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


async def connect_device(
    address: str,
    verbose: bool = False,
    *,
    privacy: bool = False,
) -> BluezState:
    info_result = await run_command_async(["bluetoothctl", "info", address])
    info_state = build_state(address, info_result, None)
    if is_device_unavailable(info_result):
        info_state = await preflight_device(address, scan_timeout=DEFAULT_SCAN_TIMEOUT)

    await ensure_sudo_ready()
    await bluez_prepare_phone_like_pairing_controller(privacy=privacy)
    pairable_result = await bluez_set_pairable(True)
    if verbose:
        print_section("bluetoothctl pairable on", pairable_result)

    info_state = await refresh_visible_device(address)
    assert_pairing_advertisement_ready(info_state, address)
    if verbose:
        print_section("post-prepare preflight", info_state.bluetoothctl)

    load_conn_params_result = await bluez_load_connection_parameters(address)
    if verbose:
        print_section("load connection parameters", load_conn_params_result)
    if load_conn_params_result.returncode != 0:
        raise RuntimeError(
            f"BlueZ load-conn-params failed for {address}: {summarize_failure(load_conn_params_result)}"
        )

    connect_result = await run_command_async(["bluetoothctl", "connect", address])
    if verbose:
        print_section("bluetoothctl connect", connect_result)

    state = await asyncio.to_thread(read_device_state, address)
    if verbose:
        print_section("bluetoothctl info", state.bluetoothctl)
        if state.busctl is not None:
            print_section("busctl introspect", state.busctl)

    if connect_result.returncode != 0 and state.connected is not True:
        raise RuntimeError(f"BlueZ connect failed for {address}: {summarize_failure(connect_result)}")
    if state.connected is False:
        raise RuntimeError(f"BlueZ reports {address} is not connected after connect attempt.")

    return BluezState(
        address=state.address,
        visible=info_state.visible if info_state.visible is not None else state.visible,
        device=info_state.device,
        name=info_state.name or state.name,
        paired=state.paired,
        trusted=state.trusted,
        connected=state.connected,
        services_resolved=state.services_resolved,
        bluetoothctl=state.bluetoothctl,
        busctl=state.busctl,
        pairing_advertisement=info_state.pairing_advertisement,
    )


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


@asynccontextmanager
async def btmon_text_capture(prefix: str = "bosch-btmon-"):
    with tempfile.NamedTemporaryFile("w+", prefix=prefix, suffix=".log", delete=False) as handle:
        trace_path = Path(handle.name)

    process = await asyncio.create_subprocess_exec(
        "sudo",
        "btmon",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    writer_task: asyncio.Task[None] | None = None

    async def pump() -> None:
        assert process.stdout is not None
        with trace_path.open("wb") as output:
            while True:
                chunk = await process.stdout.read(4096)
                if not chunk:
                    break
                output.write(chunk)

    writer_task = asyncio.create_task(pump())
    try:
        yield trace_path
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except TimeoutError:
                process.kill()
                await process.wait()
        if writer_task is not None:
            await writer_task


async def run_pair_diagnostic_attempt(
    address: str,
    *,
    pair_backend: Literal["dbus", "btmgmt"],
    privacy: bool,
    scan_timeout: float = DEFAULT_SCAN_TIMEOUT,
) -> PairAttemptSummary:
    preflight = await preflight_device(address, scan_timeout=scan_timeout)
    if preflight.visible is not True:
        return PairAttemptSummary(
            pair_backend=pair_backend,
            privacy="device" if privacy else "off",
            visible=False,
            name=preflight.name,
            assist_error="Device not visible during preflight",
            create_connection_seen=False,
            enhanced_connection_complete_seen=False,
            read_remote_features_seen=False,
            disconnect_reason=None,
            att_seen=False,
            smp_seen=False,
            highest_stage="pre_connection",
            trace_path="",
        )
    if preflight.paired is not True and preflight.pairing_advertisement is False:
        return PairAttemptSummary(
            pair_backend=pair_backend,
            privacy="device" if privacy else "off",
            visible=True,
            name=preflight.name,
            assist_error="Device visible but not in Bosch pairing advertisement mode",
            create_connection_seen=False,
            enhanced_connection_complete_seen=False,
            read_remote_features_seen=False,
            disconnect_reason=None,
            att_seen=False,
            smp_seen=False,
            highest_stage="pre_connection",
            trace_path="",
        )

    assist_error: str | None = None
    async with btmon_text_capture() as trace_path:
        try:
            await assist_connection(address, verbose=False, pair_backend=pair_backend, privacy=privacy)
        except Exception as exc:
            assist_error = format_cli_error(exc)
        await asyncio.sleep(0.5)

    trace_text = trace_path.read_text(encoding="utf-8", errors="replace")
    return summarize_btmon_trace(
        trace_text,
        pair_backend=pair_backend,
        privacy="device" if privacy else "off",
        visible=True,
        name=preflight.name,
        assist_error=assist_error,
        trace_path=str(trace_path),
    )


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


def diagnose_pair_cli() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <BLE_ADDRESS>")
        raise SystemExit(2)

    address = sys.argv[1]
    attempts = [
        ("dbus", False),
        ("dbus", True),
        ("btmgmt", False),
        ("btmgmt", True),
    ]

    try:
        for pair_backend, privacy in attempts:
            print(f"== attempt backend={pair_backend} privacy={'device' if privacy else 'off'} ==")
            summary = asyncio.run(
                run_pair_diagnostic_attempt(address, pair_backend=pair_backend, privacy=privacy)
            )
            print_pair_attempt_summary(summary)
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
        asyncio.run(connect_device(sys.argv[1], verbose=True))
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
