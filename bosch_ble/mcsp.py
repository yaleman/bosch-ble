from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


MCSP_SERVICE_UUID = "00000010-eaa2-11e9-81b4-2a2ae2dbcce4"
MCSP_RECEIVE_UUID = "00000011-eaa2-11e9-81b4-2a2ae2dbcce4"
MCSP_SEND_UUID = "00000012-eaa2-11e9-81b4-2a2ae2dbcce4"
DEFAULT_MAX_PACKET_SIZE = 244


class McspChannel(IntEnum):
    COMMAND = 0
    CHANNEL1 = 1
    CHANNEL2 = 2
    CHANNEL3 = 3
    CHANNEL4 = 4
    CHANNEL5 = 5
    CHANNEL6 = 6
    CHANNEL7 = 7


class CommandType(IntEnum):
    VERSION = 0x01
    ADVANCED_TRANSMIT_WINDOW = 0x02
    DISABLE_FLOW_CONTROL = 0x03
    MAX_SEGMENTATION_PACKET = 0x04


@dataclass(frozen=True)
class Frame:
    end_of_channel: bool
    channel: McspChannel
    payload: bytes


@dataclass(frozen=True)
class VersionCommand:
    version: int


@dataclass(frozen=True)
class AdvanceTransmitWindowCommand:
    channel: McspChannel
    advance: int


@dataclass(frozen=True)
class DisableFlowControlCommand:
    channel: McspChannel


@dataclass(frozen=True)
class MaxSegmentationPacketCommand:
    max_packet_size: int


Command = (
    VersionCommand
    | AdvanceTransmitWindowCommand
    | DisableFlowControlCommand
    | MaxSegmentationPacketCommand
)


def decode_frame(data: bytes) -> Frame:
    if len(data) < 2:
        raise ValueError("MCSP frame is shorter than 2 bytes.")
    header = data[0]
    payload_length = ((header & 0x0F) << 8) | data[1]
    frame_length = 2 + payload_length
    if len(data) != frame_length:
        raise ValueError(
            f"MCSP frame length mismatch: expected {frame_length} bytes, got {len(data)}."
        )
    return Frame(
        end_of_channel=bool(header & 0x10),
        channel=McspChannel((header >> 5) & 0x07),
        payload=data[2:],
    )


def split_frames(data: bytes) -> list[Frame]:
    frames: list[Frame] = []
    offset = 0
    while offset < len(data):
        if len(data) - offset < 2:
            raise ValueError("Trailing partial MCSP frame header.")
        header = data[offset]
        payload_length = ((header & 0x0F) << 8) | data[offset + 1]
        frame_length = 2 + payload_length
        end = offset + frame_length
        if end > len(data):
            raise ValueError("Trailing partial MCSP frame payload.")
        frames.append(decode_frame(data[offset:end]))
        offset = end
    return frames


def encode_frame(frame: Frame) -> bytes:
    payload_length = len(frame.payload)
    if payload_length > 0x0FFF:
        raise ValueError("MCSP payload is larger than 4095 bytes.")
    header = ((int(frame.channel) & 0x07) << 5) | ((payload_length >> 8) & 0x0F)
    if frame.end_of_channel:
        header |= 0x10
    return bytes((header, payload_length & 0xFF)) + frame.payload


def decode_command(payload: bytes) -> Command:
    if not payload:
        raise ValueError("MCSP command payload is empty.")
    command_type = CommandType(payload[0])
    if command_type is CommandType.VERSION:
        if len(payload) < 2:
            raise ValueError("VERSION command is truncated.")
        return VersionCommand(version=payload[1])
    if command_type is CommandType.ADVANCED_TRANSMIT_WINDOW:
        if len(payload) < 6:
            raise ValueError("ADVANCED_TRANSMIT_WINDOW command is truncated.")
        return AdvanceTransmitWindowCommand(
            channel=McspChannel(payload[1]),
            advance=int.from_bytes(payload[2:6], "big"),
        )
    if command_type is CommandType.DISABLE_FLOW_CONTROL:
        if len(payload) < 2:
            raise ValueError("DISABLE_FLOW_CONTROL command is truncated.")
        return DisableFlowControlCommand(channel=McspChannel(payload[1]))
    if command_type is CommandType.MAX_SEGMENTATION_PACKET:
        if len(payload) < 3:
            raise ValueError("MAX_SEGMENTATION_PACKET command is truncated.")
        return MaxSegmentationPacketCommand(
            max_packet_size=int.from_bytes(payload[1:3], "big")
        )
    raise ValueError(f"Unsupported MCSP command type: 0x{payload[0]:02x}")


def decode_command_frame(frame: Frame) -> Command:
    if frame.channel is not McspChannel.COMMAND:
        raise ValueError(f"MCSP frame is on {frame.channel.name}, not COMMAND.")
    return decode_command(frame.payload)


def decode_command_frames(data: bytes) -> list[Command]:
    return [decode_command_frame(frame) for frame in split_frames(data)]


def encode_command(command: Command) -> bytes:
    if isinstance(command, VersionCommand):
        return bytes((CommandType.VERSION, command.version))
    if isinstance(command, AdvanceTransmitWindowCommand):
        return bytes((CommandType.ADVANCED_TRANSMIT_WINDOW, int(command.channel))) + command.advance.to_bytes(
            4, "big"
        )
    if isinstance(command, DisableFlowControlCommand):
        return bytes((CommandType.DISABLE_FLOW_CONTROL, int(command.channel)))
    if isinstance(command, MaxSegmentationPacketCommand):
        return bytes((CommandType.MAX_SEGMENTATION_PACKET,)) + command.max_packet_size.to_bytes(
            2, "big"
        )
    raise TypeError(f"Unsupported MCSP command: {type(command).__name__}")


def encode_command_frame(command: Command) -> bytes:
    return encode_frame(
        Frame(
            end_of_channel=True,
            channel=McspChannel.COMMAND,
            payload=encode_command(command),
        )
    )
