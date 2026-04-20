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


def decode_boolean(payload: bytes) -> bool | None:
    value = _parse_varint_fields(payload).get(1)
    if value is None:
        return None
    return bool(value)


def decode_uint(payload: bytes) -> int | None:
    value = _parse_varint_fields(payload).get(1)
    return value


def decode_bike_speed(payload: bytes) -> tuple[int | None, bool | None]:
    fields = _parse_varint_fields(payload)
    value = fields.get(1)
    validity = fields.get(2)
    if validity is None:
        return value, None
    return value, bool(validity)


def _format_target(frame: messagebus.DirectedFrame) -> str:
    return frame.target_name or f"0x{frame.destination:04x}"


def _format_source(frame: messagebus.NotifyFrame) -> str:
    return frame.source_name or f"0x{frame.source:04x}"


@dataclass
class DashboardState:
    connection_status: str = "disconnected"
    startup_stage: str | None = None
    assist_mode: str | None = None
    battery_percent: int | None = None
    speed_raw: int | None = None
    charger_connected: bool | None = None
    recent_limit: int = 8
    updated_at: str | None = None
    recent_frames: deque[str] = field(init=False)
    _battery_system_percent: int | None = field(init=False, default=None)
    _battery_pack_percent: int | None = field(init=False, default=None)
    _charging_active: bool | None = field(init=False, default=None)
    _instance_charging_active: bool | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.recent_frames = deque(maxlen=self.recent_limit)

    def apply_message(self, frame: messagebus.MessageFrame) -> None:
        self.connection_status = "connected"
        self.updated_at = ts()
        self.recent_frames.append(self._summarize_frame(frame))
        if isinstance(frame, messagebus.DirectedFrame):
            self._apply_directed_frame(frame)
            return
        self._apply_notify_frame(frame)

    def apply_frame(self, frame: messagebus.DirectedFrame) -> None:
        self.apply_message(frame)

    def _apply_directed_frame(self, frame: messagebus.DirectedFrame) -> None:
        if frame.target_name != "STARTUP_STAGE":
            return
        stage = decode_uint8_nullable(frame.payload)
        if stage is not None:
            self.startup_stage = f"STAGE{stage}"

    def _apply_notify_frame(self, frame: messagebus.NotifyFrame) -> None:
        source = frame.source_name
        if source == "BATTERY_SYSTEM_STATE_OF_CHARGE_FOR_RIDER":
            self._battery_system_percent = decode_uint(frame.payload)
            self._recompute_battery_percent()
            return
        if source == "BATTERY_STATE_OF_CHARGE":
            self._battery_pack_percent = decode_uint(frame.payload)
            self._recompute_battery_percent()
            return
        if source == "BATTERY_CHARGING_ACTIVE":
            self._charging_active = decode_boolean(frame.payload)
            self._recompute_charger_connected()
            return
        if source == "BATTERY_INSTANCE_CHARGING_ACTIVE":
            self._instance_charging_active = decode_boolean(frame.payload)
            self._recompute_charger_connected()
            return
        if source == "DRIVE_UNIT_PRESENT_ASSIST_FACTOR":
            assist_factor = decode_uint(frame.payload)
            if assist_factor is not None:
                self.assist_mode = str(assist_factor)
            return
        if source == "DRIVE_UNIT_DISPLAYED_BIKE_SPEED":
            speed, valid = decode_bike_speed(frame.payload)
            if valid is True and speed is not None:
                self.speed_raw = speed
            elif valid is False:
                self.speed_raw = None

    def _recompute_battery_percent(self) -> None:
        self.battery_percent = self._battery_system_percent
        if self.battery_percent is None:
            self.battery_percent = self._battery_pack_percent

    def _recompute_charger_connected(self) -> None:
        values = [self._charging_active, self._instance_charging_active]
        if any(value is True for value in values):
            self.charger_connected = True
            return
        if any(value is not None for value in values):
            self.charger_connected = False

    def _summarize_frame(self, frame: messagebus.MessageFrame) -> str:
        if isinstance(frame, messagebus.NotifyFrame):
            summary = f"NOTIFY {_format_source(frame)}"
            if frame.payload:
                summary += f" payload={frame.payload.hex()}"
            return summary
        summary = f"{frame.message_type.name} {_format_target(frame)}"
        if frame.payload:
            summary += f" payload={frame.payload.hex()}"
        return summary


def _format_percent(value: int | None) -> str:
    if value is None:
        return "unknown"
    return f"{value}%"


def _format_speed(value: int | None) -> str:
    if value is None:
        return "unknown"
    return f"{value} raw"


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
        f"Speed      : {_format_speed(state.speed_raw)}",
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
        background_tasks: set[asyncio.Task[None]] = set()
        handshake_complete = False

        async def send_packets(packets: list[bytes]) -> None:
            for packet in packets:
                await client.write_gatt_char(send_uuid, packet, response=False)

        def schedule_packets(packets: list[bytes]) -> None:
            if not packets:
                return
            task = loop.create_task(send_packets(packets))
            background_tasks.add(task)
            task.add_done_callback(background_tasks.discard)

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
                    message = messagebus.decode_message_frame(frame.payload)
                except Exception:
                    state.recent_frames.append(
                        f"{frame.channel.name} payload={frame.payload.hex()}"
                    )
                    continue
                if handshake_complete:
                    schedule_packets(handshake.build_startup_response_packets(mcsp.encode_frame(frame)))
                state.apply_message(message)

            if not handshake_future.done() and handshake.is_bike_handshake(commands):
                handshake_future.set_result(commands)
            _print_dashboard(state)

        await client.start_notify(receive_uuid, notify_handler)
        try:
            commands = await asyncio.wait_for(
                handshake_future,
                timeout=HANDSHAKE_TIMEOUT_SECONDS,
            )
            handshake_complete = True
            for packet in handshake.build_handshake_response(commands):
                await client.write_gatt_char(send_uuid, packet, response=False)
            while not stop.is_set():
                _print_dashboard(state)
                try:
                    await asyncio.wait_for(stop.wait(), timeout=REFRESH_SECONDS)
                except TimeoutError:
                    continue
        finally:
            if background_tasks:
                await asyncio.gather(*background_tasks, return_exceptions=True)
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
