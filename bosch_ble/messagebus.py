from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class MessageType(IntEnum):
    READ = 0x0
    READ_RESPONSE = 0x1
    WRITE = 0x2
    WRITE_RESPONSE = 0x3
    RPC = 0x4
    RPC_RESPONSE = 0x5
    SUBSCRIBE = 0x6
    SUBSCRIBE_RESPONSE = 0x7
    UNSUBSCRIBE = 0x8
    UNSUBSCRIBE_RESPONSE = 0x9
    NOTIFY = 0xA


class ResponseStatusCode(IntEnum):
    SUCCESS = 0x00
    FAILURE = 0x01
    NO_ROUTE_FOUND = 0x02
    NO_ACCESS = 0x03
    UNSUPPORTED = 0x04
    INVALID_PARAMETER = 0x05
    UNKNOWN_ERROR = 0xFF

    @classmethod
    def from_byte(cls, value: int) -> "ResponseStatusCode":
        try:
            return cls(value)
        except ValueError:
            return cls.UNKNOWN_ERROR


ADDRESS_NAMES: dict[int, str] = {
    0x0088: "BATTERY_STATE_OF_CHARGE",
    0x008A: "BATTERY_CHARGING_ACTIVE",
    0x00BC: "BATTERY_SYSTEM_STATE_OF_CHARGE_FOR_RIDER",
    0x00C4: "BATTERY_INSTANCE_CHARGING_ACTIVE",
    0x181E: "DRIVE_UNIT_PRESENT_ASSIST_FACTOR",
    0x182D: "DRIVE_UNIT_DISPLAYED_BIKE_SPEED",
    0x4081: "UI_PRIORITY",
    0x4082: "FEATURE_STREAMING_ALERT",
    0x4083: "FEATURE_STREAMING_ALERT_RESPONSE",
    0x4084: "FEATURE_STREAMING_OPTION_RESPONSE",
    0x4085: "ALTITUDE",
    0x4086: "MAXIMUM_ALTITUDE",
    0x4087: "ASCENT",
    0x4088: "DESCENT",
    0x4089: "STATE_OF_CHARGE",
    0x408A: "ROAD_SLOPE",
    0x408B: "CURRENT_COUNTRY",
    0x4091: "SOFTWARE_VERSION",
    0x4092: "DATA_MODEL_VERSION",
    0x4093: "MESSAGE_BUS_BUSINESS_LOGIC_VERSION",
    0x4094: "HEART_RATE",
    0x4095: "HEART_RATE_STATUS",
    0x4096: "NAVIGATION_CURRENT_STATUS",
    0x4097: "NAVIGATION_DISTANCE_TO_DESTINATION",
    0x4098: "NAVIGATION_ETA",
    0x4099: "NAVIGATION_TIME_TO_DESTINATION",
    0x409A: "ALTITUDE_GRAPH_AVAILABLE_SAMPLES",
    0x409B: "GET_ALTITUDE_GRAPH",
    0x409C: "UPDATE_ISSUE_VISUALIZATION",
    0x409D: "VISUALIZABLE_ISSUE_TYPES",
    0x409F: "MOBILE_APP_FEATURE_PROPERTIES_RELEASE4",
    0x40A0: "LOCATION",
    0x40A1: "NAVIGATION_ADVICE",
    0x40A2: "SYSTEM_STATE_OF_CHARGE_FOR_RIDER_AT_DESTINATION",
    0x40A3: "PHONE_CHARGING",
    0x40A4: "USER_INFO",
    0x40A8: "SPEED",
    0x40A9: "STARTUP_STAGE",
    0x40AA: "MOBILE_APP_STATIC_FEATURE_PROPERTIES",
    0xF809: "ASSIST_MODE_USAGE",
}


STARTUP_PROVIDER_PAYLOADS: dict[int, bytes] = {
    0x4081: bytes.fromhex("0824"),
    0x4082: b"",
    0x4085: b"",
    0x4086: b"",
    0x4087: b"",
    0x4088: b"",
    0x4089: b"",
    0x408A: b"",
    0x408B: b"",
    0x4091: b"",
    0x4092: b"",
    0x4093: b"",
    0x4094: b"",
    0x4095: b"",
    0x4096: b"",
    0x4097: b"",
    0x4098: b"",
    0x4099: b"",
    0x409A: b"",
    0x409D: bytes.fromhex("0800080108020803"),
    0x409F: bytes.fromhex("0801"),
    0x40A0: b"",
    0x40A1: b"",
    0x40A2: b"",
    0x40A3: b"",
    0x40A4: b"",
    0x40A8: b"",
    0x40AA: b"",
}


@dataclass(frozen=True)
class DirectedFrame:
    source: int
    destination: int
    message_type: MessageType
    sequence: int
    payload: bytes
    status_code: ResponseStatusCode = ResponseStatusCode.SUCCESS

    @property
    def target_name(self) -> str | None:
        return ADDRESS_NAMES.get(self.destination)

    @property
    def source_name(self) -> str | None:
        return ADDRESS_NAMES.get(self.source)


@dataclass(frozen=True)
class NotifyFrame:
    source: int
    payload: bytes
    message_type: MessageType = MessageType.NOTIFY

    @property
    def source_name(self) -> str | None:
        return ADDRESS_NAMES.get(self.source)


MessageFrame = DirectedFrame | NotifyFrame


def _decode_address(high: int, low: int) -> int:
    return ((high & 0x7F) << 8) | low


def _encode_address(address: int, *, set_msb: bool = False) -> bytes:
    high = (address >> 8) & 0x7F
    if set_msb:
        high |= 0x80
    return bytes((high, address & 0xFF))


def _is_response_type(message_type: MessageType) -> bool:
    return message_type in {
        MessageType.READ_RESPONSE,
        MessageType.WRITE_RESPONSE,
        MessageType.RPC_RESPONSE,
        MessageType.SUBSCRIBE_RESPONSE,
        MessageType.UNSUBSCRIBE_RESPONSE,
    }


def _coerce_bytes(data: bytes | str) -> bytes:
    if isinstance(data, str):
        return bytes.fromhex(data)
    return data


def decode_directed_frame(data: bytes | str) -> DirectedFrame:
    raw = _coerce_bytes(data)
    if len(raw) < 5:
        raise ValueError("Directed frame is shorter than 5 bytes.")

    source = _decode_address(raw[0], raw[1])
    destination = _decode_address(raw[2], raw[3])
    type_and_sequence = raw[4]
    message_type = MessageType((type_and_sequence >> 4) & 0x0F)
    sequence = type_and_sequence & 0x0F
    status_code = ResponseStatusCode.SUCCESS
    payload_offset = 5

    if _is_response_type(message_type) and not (raw[2] & 0x80):
        if len(raw) < 6:
            raise ValueError("Response frame is missing a status byte.")
        status_code = ResponseStatusCode.from_byte(raw[5])
        payload_offset = 6

    return DirectedFrame(
        source=source,
        destination=destination,
        message_type=message_type,
        sequence=sequence,
        payload=raw[payload_offset:],
        status_code=status_code,
    )


def decode_message_frame(data: bytes | str) -> MessageFrame:
    raw = _coerce_bytes(data)
    if len(raw) < 2:
        raise ValueError("Message frame is shorter than 2 bytes.")
    if raw[0] & 0x80:
        return NotifyFrame(
            source=_decode_address(raw[0], raw[1]),
            payload=raw[2:],
        )
    return decode_directed_frame(raw)


def _encode_response(
    request: DirectedFrame,
    response_type: MessageType,
    payload: bytes = b"",
    status_code: ResponseStatusCode = ResponseStatusCode.SUCCESS,
) -> bytes:
    if not _is_response_type(response_type):
        raise ValueError(f"{response_type.name} is not a response message type.")

    destination = _encode_address(
        request.source,
        set_msb=status_code is ResponseStatusCode.SUCCESS,
    )
    encoded = bytearray()
    encoded.extend(_encode_address(request.destination))
    encoded.extend(destination)
    encoded.append(((int(response_type) & 0x0F) << 4) | (request.sequence & 0x0F))
    if status_code is not ResponseStatusCode.SUCCESS:
        encoded.append(int(status_code) & 0xFF)
    encoded.extend(payload)
    return bytes(encoded)


def encode_read_response(
    request: DirectedFrame,
    payload: bytes,
    status_code: ResponseStatusCode = ResponseStatusCode.SUCCESS,
) -> bytes:
    return _encode_response(
        request,
        MessageType.READ_RESPONSE,
        payload=payload,
        status_code=status_code,
    )


def encode_write_response(
    request: DirectedFrame,
    payload: bytes = b"",
    status_code: ResponseStatusCode = ResponseStatusCode.SUCCESS,
) -> bytes:
    return _encode_response(
        request,
        MessageType.WRITE_RESPONSE,
        payload=payload,
        status_code=status_code,
    )


def encode_rpc_response(
    request: DirectedFrame,
    payload: bytes = b"",
    status_code: ResponseStatusCode = ResponseStatusCode.SUCCESS,
) -> bytes:
    return _encode_response(
        request,
        MessageType.RPC_RESPONSE,
        payload=payload,
        status_code=status_code,
    )


def encode_subscribe_response(
    request: DirectedFrame,
    payload: bytes = b"",
    status_code: ResponseStatusCode = ResponseStatusCode.SUCCESS,
) -> bytes:
    return _encode_response(
        request,
        MessageType.SUBSCRIBE_RESPONSE,
        payload=payload,
        status_code=status_code,
    )


def encode_unsubscribe_response(
    request: DirectedFrame,
    payload: bytes = b"",
    status_code: ResponseStatusCode = ResponseStatusCode.SUCCESS,
) -> bytes:
    return _encode_response(
        request,
        MessageType.UNSUBSCRIBE_RESPONSE,
        payload=payload,
        status_code=status_code,
    )


def encode_notify(source: int, payload: bytes) -> bytes:
    return _encode_address(source, set_msb=True) + payload


def format_message_frame(frame: MessageFrame) -> str:
    if isinstance(frame, NotifyFrame):
        source = frame.source_name or f"0x{frame.source:04x}"
        summary = f"NOTIFY {source}"
    else:
        target = frame.target_name or f"0x{frame.destination:04x}"
        summary = f"{frame.message_type.name} {target}"
    if frame.payload:
        summary += f" payload={frame.payload.hex()}"
    return summary
