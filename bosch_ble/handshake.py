#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from bleak import BleakClient

from bosch_ble import dump_gatt, mcsp, messagebus as messagebus_mod


HANDSHAKE_TIMEOUT_SECONDS = 10.0
POST_HANDSHAKE_WAIT_SECONDS = 1.0
NON_COMMAND_CHANNELS = tuple(
    channel for channel in mcsp.McspChannel if channel is not mcsp.McspChannel.COMMAND
)
STARTUP_WRITE_ADDRESSES = {0x40A9}
STARTUP_RPC_ADDRESSES = {0x409C}


def ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def format_cli_error(exc: Exception) -> str:
    return str(exc) or type(exc).__name__


def normalize_uuid(value: object) -> str:
    return str(value).lower()


def find_mcsp_transport(services: object) -> tuple[str, str]:
    receive_uuid: str | None = None
    send_uuid: str | None = None
    for service in services:
        if normalize_uuid(getattr(service, "uuid", "")) != mcsp.MCSP_SERVICE_UUID:
            continue
        for char in getattr(service, "characteristics", []):
            uuid = normalize_uuid(getattr(char, "uuid", ""))
            if uuid == mcsp.MCSP_RECEIVE_UUID:
                receive_uuid = uuid
            if uuid == mcsp.MCSP_SEND_UUID:
                send_uuid = uuid
    if receive_uuid is None or send_uuid is None:
        raise RuntimeError("MCSP transport characteristics were not found.")
    return receive_uuid, send_uuid


def is_bike_handshake(commands: list[mcsp.Command]) -> bool:
    version_ok = any(
        isinstance(command, mcsp.VersionCommand) and command.version == 3
        for command in commands
    )
    max_packet_seen = any(
        isinstance(command, mcsp.MaxSegmentationPacketCommand) for command in commands
    )
    advanced_channels = {
        command.channel
        for command in commands
        if isinstance(command, mcsp.AdvanceTransmitWindowCommand)
    }
    return version_ok and max_packet_seen and advanced_channels == set(NON_COMMAND_CHANNELS)


def build_handshake_response(
    commands: list[mcsp.Command],
    local_packet_size: int = mcsp.DEFAULT_MAX_PACKET_SIZE,
) -> list[bytes]:
    remote_packet_sizes = [
        command.max_packet_size
        for command in commands
        if isinstance(command, mcsp.MaxSegmentationPacketCommand)
    ]
    max_packet_size = local_packet_size
    if remote_packet_sizes:
        max_packet_size = min(max_packet_size, min(remote_packet_sizes))
    response_commands: list[mcsp.Command] = [
        mcsp.VersionCommand(version=3),
        mcsp.MaxSegmentationPacketCommand(max_packet_size=max_packet_size),
    ]
    response_commands.extend(
        mcsp.DisableFlowControlCommand(channel=channel)
        for channel in NON_COMMAND_CHANNELS
    )
    return [mcsp.encode_command_frame(command) for command in response_commands]


def build_startup_response_packets(messagebus: bytes) -> list[bytes]:
    frame = mcsp.decode_frame(messagebus)
    if frame.channel is mcsp.McspChannel.COMMAND:
        return []

    decoded = messagebus_mod.decode_message_frame(frame.payload)
    if not isinstance(decoded, messagebus_mod.DirectedFrame):
        return []

    responses: list[bytes] = []
    payload = messagebus_mod.STARTUP_PROVIDER_PAYLOADS.get(decoded.destination)
    if decoded.message_type is messagebus_mod.MessageType.READ:
        if payload is None:
            responses.append(
                messagebus_mod.encode_read_response(
                    decoded,
                    b"",
                    status_code=messagebus_mod.ResponseStatusCode.UNSUPPORTED,
                )
            )
        else:
            responses.append(messagebus_mod.encode_read_response(decoded, payload))
    elif decoded.message_type is messagebus_mod.MessageType.SUBSCRIBE:
        if payload is None:
            responses.append(
                messagebus_mod.encode_subscribe_response(
                    decoded,
                    status_code=messagebus_mod.ResponseStatusCode.UNSUPPORTED,
                )
            )
        else:
            responses.append(messagebus_mod.encode_subscribe_response(decoded))
            responses.append(messagebus_mod.encode_notify(decoded.destination, payload))
    elif decoded.message_type is messagebus_mod.MessageType.UNSUBSCRIBE:
        if payload is None:
            responses.append(
                messagebus_mod.encode_unsubscribe_response(
                    decoded,
                    status_code=messagebus_mod.ResponseStatusCode.UNSUPPORTED,
                )
            )
        else:
            responses.append(messagebus_mod.encode_unsubscribe_response(decoded))
    elif decoded.message_type is messagebus_mod.MessageType.WRITE:
        if (
            decoded.destination in STARTUP_WRITE_ADDRESSES
            or decoded.destination in messagebus_mod.STARTUP_PROVIDER_PAYLOADS
        ):
            responses.append(messagebus_mod.encode_write_response(decoded))
        else:
            responses.append(
                messagebus_mod.encode_write_response(
                    decoded,
                    status_code=messagebus_mod.ResponseStatusCode.UNSUPPORTED,
                )
            )
    elif decoded.message_type is messagebus_mod.MessageType.RPC:
        if decoded.destination in STARTUP_RPC_ADDRESSES:
            responses.append(messagebus_mod.encode_rpc_response(decoded))
        else:
            responses.append(
                messagebus_mod.encode_rpc_response(
                    decoded,
                    status_code=messagebus_mod.ResponseStatusCode.UNSUPPORTED,
                )
            )

    return [
        mcsp.encode_frame(
            mcsp.Frame(
                end_of_channel=True,
                channel=frame.channel,
                payload=response,
            )
        )
        for response in responses
    ]


async def main(address: str, out_file: str = "ble_handshake.txt") -> None:
    path = Path(out_file)
    print(f"Connecting to {address} ...", flush=True)
    print(f"Logging to {path}", flush=True)

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    state = await dump_gatt.prepare_connection(address)
    target = dump_gatt.client_target_for_state(state)

    async with BleakClient(target, timeout=20.0) as client:
        print(f"Connected: {client.is_connected}", flush=True)
        if not client.is_connected:
            raise RuntimeError("Failed to connect")

        receive_uuid, send_uuid = find_mcsp_transport(client.services)

        with path.open("a", encoding="utf-8") as fh:
            background_tasks: set[asyncio.Task[None]] = set()
            handshake_complete = False

            def emit(line: str) -> None:
                print(line, flush=True)
                fh.write(f"{line}\n")
                fh.flush()

            async def send_packets(packets: list[bytes]) -> None:
                for packet in packets:
                    emit(f"{ts()} SEND hex={packet.hex()}")
                    await client.write_gatt_char(send_uuid, packet, response=False)

            def schedule_packets(packets: list[bytes]) -> None:
                if not packets:
                    return
                task = loop.create_task(send_packets(packets))
                background_tasks.add(task)
                task.add_done_callback(background_tasks.discard)

            emit(f"{ts()} CONNECTED {address}")
            handshake_future: asyncio.Future[list[mcsp.Command]] = loop.create_future()

            def notify_handler(sender: Any, data: bytearray) -> None:
                payload = bytes(data)
                emit(f"{ts()} NOTIFY sender={sender} hex={payload.hex()} raw={payload!r}")
                try:
                    frames = mcsp.split_frames(payload)
                except Exception as exc:
                    emit(f"{ts()} DECODE_FAILED error={exc}")
                    return
                commands: list[mcsp.Command] = []
                for frame in frames:
                    emit(
                        f"{ts()} FRAME channel={frame.channel.name} end={frame.end_of_channel} hex={frame.payload.hex()}"
                    )
                    if frame.channel is not mcsp.McspChannel.COMMAND:
                        if handshake_complete:
                            schedule_packets(
                                build_startup_response_packets(mcsp.encode_frame(frame))
                            )
                        continue
                    try:
                        command = mcsp.decode_command_frame(frame)
                    except Exception as exc:
                        emit(f"{ts()} DECODE_FAILED error={exc}")
                        continue
                    commands.append(command)
                    emit(f"{ts()} RECV command={command!r}")
                if not handshake_future.done() and is_bike_handshake(commands):
                    handshake_future.set_result(commands)

            await client.start_notify(receive_uuid, notify_handler)
            try:
                commands = await asyncio.wait_for(
                    handshake_future,
                    timeout=HANDSHAKE_TIMEOUT_SECONDS,
                )
                handshake_complete = True
                await send_packets(build_handshake_response(commands))
                if not stop.is_set():
                    await asyncio.sleep(POST_HANDSHAKE_WAIT_SECONDS)
            finally:
                if background_tasks:
                    await asyncio.gather(*background_tasks, return_exceptions=True)
                await client.stop_notify(receive_uuid)


def cli() -> None:
    if len(sys.argv) not in {2, 3}:
        print(f"Usage: {sys.argv[0]} <BLE_ADDRESS> [output_file]")
        raise SystemExit(2)

    address = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) == 3 else "ble_handshake.txt"
    try:
        asyncio.run(main(address, output))
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {format_cli_error(exc)}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
