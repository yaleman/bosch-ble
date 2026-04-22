from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Callable

from bleak import BleakClient

from bosch_ble import dump_gatt, mcsp, messagebus


NON_COMMAND_CHANNELS = tuple(
    channel for channel in mcsp.McspChannel if channel is not mcsp.McspChannel.COMMAND
)

StartupResponder = Callable[[mcsp.Frame, messagebus.MessageFrame], list[bytes]]
FrameHandler = Callable[[mcsp.Frame], None]
CommandHandler = Callable[[mcsp.Command], None]
MessageHandler = Callable[[mcsp.Frame, messagebus.MessageFrame], None]
DecodeErrorHandler = Callable[[bytes | mcsp.Frame, Exception], None]
NotifyHandler = Callable[[Any, bytes], None]
SendHandler = Callable[[bytes], None]


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


@asynccontextmanager
async def connected_client(address: str, timeout: float = 20.0):
    last_error: Exception | None = None
    for attempt in range(1, dump_gatt.DISCOVERY_RETRY_ATTEMPTS + 1):
        try:
            state = await dump_gatt.prepare_connection(address)
            target = dump_gatt.client_target_for_state(state)
            async with BleakClient(target, timeout=timeout) as client:
                if not client.is_connected:
                    raise RuntimeError("Failed to connect")
                try:
                    await dump_gatt.stage_bosch_security(client, address)
                except RuntimeError as exc:
                    if str(exc) != "Bosch security descriptor was not found.":
                        raise
                yield client
                return
        except Exception as exc:
            last_error = exc
            message = dump_gatt.retry_message(exc, address)
            if attempt < dump_gatt.DISCOVERY_RETRY_ATTEMPTS and message is not None:
                print(message)
                await asyncio.sleep(attempt)
                continue
            raise

    if last_error is not None:
        raise last_error


class McspLiveSession:
    def __init__(
        self,
        client: BleakClient,
        receive_uuid: str,
        send_uuid: str,
        *,
        startup_responder: StartupResponder | None = None,
        on_notify: NotifyHandler | None = None,
        on_frame: FrameHandler | None = None,
        on_command: CommandHandler | None = None,
        on_message: MessageHandler | None = None,
        on_decode_error: DecodeErrorHandler | None = None,
        on_send: SendHandler | None = None,
    ) -> None:
        self.client = client
        self.receive_uuid = receive_uuid
        self.send_uuid = send_uuid
        self.startup_responder = startup_responder
        self.on_notify = on_notify
        self.on_frame = on_frame
        self.on_command = on_command
        self.on_message = on_message
        self.on_decode_error = on_decode_error
        self.on_send = on_send
        self._send_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._writer_task: asyncio.Task[None] | None = None
        self._startup_packets_pending: list[bytes] = []
        self._handshake_commands: list[mcsp.Command] = []
        self._startup_ready = False
        self._loop = asyncio.get_running_loop()
        self._handshake_future: asyncio.Future[list[mcsp.Command]] = self._loop.create_future()

    async def start(self) -> None:
        self._writer_task = self._loop.create_task(self._writer())
        await self.client.start_notify(self.receive_uuid, self._notify_handler)

    async def stop(self) -> None:
        await self.client.stop_notify(self.receive_uuid)
        await self._send_queue.join()
        await self._send_queue.put(None)
        if self._writer_task is not None:
            await self._writer_task

    async def wait_for_handshake(self, timeout: float) -> list[mcsp.Command]:
        return await asyncio.wait_for(self._handshake_future, timeout=timeout)

    async def queue_handshake_response(self, commands: list[mcsp.Command]) -> None:
        self.queue_packets(build_handshake_response(commands))
        self._startup_ready = True
        if self._startup_packets_pending:
            self.queue_packets(self._startup_packets_pending)
            self._startup_packets_pending = []

    def queue_packets(self, packets: list[bytes]) -> None:
        for packet in packets:
            self._send_queue.put_nowait(packet)

    async def _writer(self) -> None:
        while True:
            packet = await self._send_queue.get()
            if packet is None:
                self._send_queue.task_done()
                return
            try:
                if self.on_send is not None:
                    self.on_send(packet)
                await self.client.write_gatt_char(self.send_uuid, packet, response=False)
            finally:
                self._send_queue.task_done()

    def _notify_handler(self, sender: Any, data: bytearray) -> None:
        payload = bytes(data)
        if self.on_notify is not None:
            self.on_notify(sender, payload)
        try:
            frames = mcsp.split_frames(payload)
        except Exception as exc:
            if self.on_decode_error is not None:
                self.on_decode_error(payload, exc)
            return

        commands: list[mcsp.Command] = []
        for frame in frames:
            if self.on_frame is not None:
                self.on_frame(frame)
            if frame.channel is mcsp.McspChannel.COMMAND:
                try:
                    command = mcsp.decode_command_frame(frame)
                except Exception as exc:
                    if self.on_decode_error is not None:
                        self.on_decode_error(frame, exc)
                    continue
                commands.append(command)
                self._handshake_commands.append(command)
                if self.on_command is not None:
                    self.on_command(command)
                continue

            try:
                decoded = messagebus.decode_message_frame(frame.payload)
            except Exception as exc:
                if self.on_decode_error is not None:
                    self.on_decode_error(frame, exc)
                continue
            if self.on_message is not None:
                self.on_message(frame, decoded)
            if self.startup_responder is None:
                continue
            packets = self.startup_responder(frame, decoded)
            if not packets:
                continue
            if self._startup_ready:
                self.queue_packets(packets)
            else:
                self._startup_packets_pending.extend(packets)

        if not self._handshake_future.done() and is_bike_handshake(self._handshake_commands):
            self._handshake_future.set_result(list(self._handshake_commands))
