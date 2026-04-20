from __future__ import annotations

import asyncio
import signal
import sys
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from bleak import BleakClient

from bosch_ble import dump_gatt, handshake, mcsp, messagebus


REFRESH_SECONDS = 1.0
HANDSHAKE_TIMEOUT_SECONDS = 10.0
CLEAR_SCREEN = "\x1b[2J\x1b[H"


def format_cli_error(exc: Exception) -> str:
    return str(exc) or type(exc).__name__


def ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    value = 0
    shift = 0
    index = offset
    while index < len(data):
        byte = data[index]
        value |= (byte & 0x7F) << shift
        index += 1
        if not byte & 0x80:
            return value, index
        shift += 7
    raise ValueError("Truncated protobuf varint.")


def _parse_varint_fields(payload: bytes) -> dict[int, int]:
    values: dict[int, int] = {}
    offset = 0
    while offset < len(payload):
        key, offset = _parse_varint(payload, offset)
        field_number = key >> 3
        wire_type = key & 0x07
        if wire_type != 0:
            raise ValueError(f"Unsupported wire type {wire_type}.")
        value, offset = _parse_varint(payload, offset)
        values[field_number] = value
    return values


def decode_uint8_nullable(payload: bytes) -> int | None:
    return _parse_varint_fields(payload).get(1)


def decode_boolean_nullable(payload: bytes) -> bool | None:
    value = _parse_varint_fields(payload).get(1)
    if value is None:
        return None
    return bool(value)


def decode_gnss_speed(payload: bytes) -> float | None:
    value = _parse_varint_fields(payload).get(1)
    if value is None:
        return None
    return value / 100.0


def _format_target(frame: messagebus.DirectedFrame) -> str:
    return frame.target_name or f"0x{frame.destination:04x}"


@dataclass
class DashboardState:
    connection_status: str = "disconnected"
    startup_stage: str | None = None
    assist_mode: str | None = None
    battery_percent: int | None = None
    speed_kmh: float | None = None
    charger_connected: bool | None = None
    recent_limit: int = 8
    updated_at: str | None = None
    recent_frames: deque[str] = field(init=False)

    def __post_init__(self) -> None:
        self.recent_frames = deque(maxlen=self.recent_limit)

    def apply_frame(self, frame: messagebus.DirectedFrame) -> None:
        self.connection_status = "connected"
        self.updated_at = ts()
        self.recent_frames.append(self._summarize_frame(frame))
        target = frame.target_name
        if target == "STARTUP_STAGE":
            stage = decode_uint8_nullable(frame.payload)
            if stage is not None:
                self.startup_stage = f"STAGE{stage}"
            return
        if target == "STATE_OF_CHARGE":
            self.battery_percent = decode_uint8_nullable(frame.payload)
            return
        if target == "PHONE_CHARGING":
            self.charger_connected = decode_boolean_nullable(frame.payload)
            return
        if target in {"SPEED", "DRIVE_UNIT_DISPLAYED_BIKE_SPEED"}:
            self.speed_kmh = decode_gnss_speed(frame.payload)
            return
        if target == "DRIVE_UNIT_PRESENT_ASSIST_FACTOR":
            assist_factor = decode_uint8_nullable(frame.payload)
            if assist_factor is not None:
                self.assist_mode = f"{assist_factor}% assist"

    def _summarize_frame(self, frame: messagebus.DirectedFrame) -> str:
        summary = f"{frame.message_type.name} {_format_target(frame)}"
        if frame.payload:
            summary += f" payload={frame.payload.hex()}"
        return summary


def _format_percent(value: int | None) -> str:
    if value is None:
        return "unknown"
    return f"{value}%"


def _format_speed(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:.2f} km/h"


def _format_charger(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return "charging" if value else "unplugged"


def render_dashboard(state: DashboardState) -> str:
    lines = [
        "Bosch BLE Dashboard",
        "",
        f"Connection : {state.connection_status}",
        f"Startup    : {state.startup_stage or 'unknown'}",
        f"Assist     : {state.assist_mode or 'unknown'}",
        f"Battery    : {_format_percent(state.battery_percent)}",
        f"Speed      : {_format_speed(state.speed_kmh)}",
        f"Charger    : {_format_charger(state.charger_connected)}",
    ]
    if state.updated_at:
        lines.append(f"Updated    : {state.updated_at}")
    lines.extend(["", "Recent frames:"])
    if state.recent_frames:
        lines.extend(state.recent_frames)
    else:
        lines.append("waiting for data")
    return "\n".join(lines)


def _print_dashboard(state: DashboardState) -> None:
    print(f"{CLEAR_SCREEN}{render_dashboard(state)}", end="\n", flush=True)


async def main(address: str) -> None:
    print(f"Connecting to {address} ...", flush=True)
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    state = DashboardState(connection_status="connecting")
    _print_dashboard(state)

    bluez_state = await dump_gatt.prepare_connection(address)
    target = dump_gatt.client_target_for_state(bluez_state)

    async with BleakClient(target, timeout=20.0) as client:
        state.connection_status = "connected" if client.is_connected else "disconnected"
        _print_dashboard(state)
        if not client.is_connected:
            raise RuntimeError("Failed to connect")

        receive_uuid, send_uuid = handshake.find_mcsp_transport(client.services)
        handshake_future: asyncio.Future[list[mcsp.Command]] = loop.create_future()

        def notify_handler(sender: Any, data: bytearray) -> None:
            del sender
            payload = bytes(data)
            try:
                frames = mcsp.split_frames(payload)
            except Exception as exc:
                state.recent_frames.append(f"DECODE_FAILED {exc}")
                _print_dashboard(state)
                return

            commands: list[mcsp.Command] = []
            for frame in frames:
                if frame.channel is mcsp.McspChannel.COMMAND:
                    try:
                        command = mcsp.decode_command_frame(frame)
                    except Exception as exc:
                        state.recent_frames.append(f"DECODE_FAILED {exc}")
                        continue
                    commands.append(command)
                    continue

                try:
                    directed = messagebus.decode_directed_frame(frame.payload)
                except Exception:
                    state.recent_frames.append(
                        f"{frame.channel.name} payload={frame.payload.hex()}"
                    )
                    continue
                state.apply_frame(directed)

            if not handshake_future.done() and handshake.is_bike_handshake(commands):
                handshake_future.set_result(commands)
            _print_dashboard(state)

        await client.start_notify(receive_uuid, notify_handler)
        try:
            commands = await asyncio.wait_for(
                handshake_future,
                timeout=HANDSHAKE_TIMEOUT_SECONDS,
            )
            for packet in handshake.build_handshake_response(commands):
                await client.write_gatt_char(send_uuid, packet, response=False)
            while not stop.is_set():
                _print_dashboard(state)
                try:
                    await asyncio.wait_for(stop.wait(), timeout=REFRESH_SECONDS)
                except TimeoutError:
                    continue
        finally:
            await client.stop_notify(receive_uuid)
            state.connection_status = "disconnected"
            _print_dashboard(state)


def cli() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <BLE_ADDRESS>")
        raise SystemExit(2)

    address = sys.argv[1]
    try:
        asyncio.run(main(address))
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {format_cli_error(exc)}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
