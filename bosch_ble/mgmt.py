from __future__ import annotations

import ctypes
import errno
import socket
import struct
import sys
from dataclasses import dataclass


AF_BLUETOOTH = 31
BTPROTO_HCI = 1
HCI_CHANNEL_CONTROL = 3
HCI_DEV_NONE = 0xFFFF

MGMT_OP_LOAD_CONN_PARAM = 0x0035
MGMT_EV_CMD_COMPLETE = 0x0001
MGMT_EV_CMD_STATUS = 0x0002
MGMT_STATUS_SUCCESS = 0x00

LE_PUBLIC_ADDRESS = 0x01


@dataclass(frozen=True)
class LoadConnectionParameters:
    address: str
    controller_index: int = 0
    address_type: int = LE_PUBLIC_ADDRESS
    min_interval: int = 24
    max_interval: int = 24
    latency: int = 0
    timeout: int = 72


class SockaddrHci(ctypes.Structure):
    _fields_ = [
        ("hci_family", ctypes.c_ushort),
        ("hci_dev", ctypes.c_ushort),
        ("hci_channel", ctypes.c_ushort),
    ]


def bdaddr_to_bytes(address: str) -> bytes:
    parts = address.split(":")
    if len(parts) != 6:
        raise ValueError(f"Invalid Bluetooth address: {address}")
    try:
        octets = bytes(int(part, 16) for part in parts)
    except ValueError as exc:
        raise ValueError(f"Invalid Bluetooth address: {address}") from exc
    return bytes(reversed(octets))


def encode_load_connection_parameters(command: LoadConnectionParameters) -> bytes:
    payload = struct.pack(
        "<H6sBHHHH",
        1,
        bdaddr_to_bytes(command.address),
        command.address_type,
        command.min_interval,
        command.max_interval,
        command.latency,
        command.timeout,
    )
    header = struct.pack(
        "<HHH",
        MGMT_OP_LOAD_CONN_PARAM,
        command.controller_index,
        len(payload),
    )
    return header + payload


def bind_mgmt_socket(sock: socket.socket) -> None:
    addr = SockaddrHci(
        hci_family=AF_BLUETOOTH,
        hci_dev=HCI_DEV_NONE,
        hci_channel=HCI_CHANNEL_CONTROL,
    )
    libc = ctypes.CDLL(None, use_errno=True)
    result = libc.bind(
        sock.fileno(),
        ctypes.byref(addr),
        ctypes.sizeof(addr),
    )
    if result != 0:
        errno = ctypes.get_errno()
        raise OSError(errno, "bind(HCI_CHANNEL_CONTROL) failed")


def receive_mgmt_response(sock: socket.socket) -> tuple[int, int]:
    while True:
        packet = sock.recv(4096)
        if len(packet) < 6:
            continue
        event_code, _index, payload_len = struct.unpack_from("<HHH", packet, 0)
        payload = packet[6 : 6 + payload_len]
        if event_code == MGMT_EV_CMD_COMPLETE and len(payload) >= 3:
            opcode, status = struct.unpack_from("<HB", payload, 0)
            if opcode == MGMT_OP_LOAD_CONN_PARAM:
                return event_code, status
        if event_code == MGMT_EV_CMD_STATUS and len(payload) >= 3:
            opcode, status = struct.unpack_from("<HB", payload, 0)
            if opcode == MGMT_OP_LOAD_CONN_PARAM:
                return event_code, status


def status_text(status: int) -> str:
    return {
        0x00: "Success",
        0x01: "Unknown Command",
        0x02: "Not Connected",
        0x03: "Failed",
        0x04: "Connect Failed",
        0x05: "Authentication Failed",
        0x06: "Not Paired",
        0x07: "No Resources",
        0x08: "Timeout",
        0x09: "Already Connected",
        0x0A: "Busy",
        0x0B: "Rejected",
        0x0C: "Not Supported",
        0x0D: "Invalid Parameters",
        0x0E: "Disconnected",
        0x0F: "Not Powered",
        0x10: "Cancelled",
        0x11: "Invalid Index",
        0x12: "RFKilled",
        0x13: "Already Paired",
        0x14: "Permission Denied",
    }.get(status, f"Unknown status 0x{status:02x}")


def load_connection_parameters(command: LoadConnectionParameters) -> None:
    packet = encode_load_connection_parameters(command)
    with socket.socket(AF_BLUETOOTH, socket.SOCK_RAW, BTPROTO_HCI) as sock:
        sock.settimeout(5.0)
        bind_mgmt_socket(sock)
        try:
            sock.sendall(packet)
        except OSError as exc:
            if exc.errno == errno.ENOMEM:
                raise PermissionError(
                    "Trusted BlueZ mgmt socket required for write commands; "
                    "run with sudo or CAP_NET_ADMIN"
                ) from exc
            raise
        _event_code, status = receive_mgmt_response(sock)
    if status != MGMT_STATUS_SUCCESS:
        raise RuntimeError(status_text(status))


def parse_args(argv: list[str]) -> LoadConnectionParameters:
    if len(argv) != 16 or argv[1] != "load-conn-params":
        raise SystemExit(
            "Usage: python -m bosch_ble.mgmt load-conn-params --address <BLE_ADDRESS> "
            "--controller-index <index> --address-type <type> --min-interval <units> "
            "--max-interval <units> --latency <units> --timeout <units>"
        )
    parsed: dict[str, str] = {}
    for i in range(2, len(argv), 2):
        parsed[argv[i]] = argv[i + 1]
    return LoadConnectionParameters(
        address=parsed["--address"],
        controller_index=int(parsed["--controller-index"]),
        address_type=int(parsed["--address-type"]),
        min_interval=int(parsed["--min-interval"]),
        max_interval=int(parsed["--max-interval"]),
        latency=int(parsed["--latency"]),
        timeout=int(parsed["--timeout"]),
    )


def cli() -> None:
    command = parse_args(sys.argv)
    try:
        load_connection_parameters(command)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    cli()
