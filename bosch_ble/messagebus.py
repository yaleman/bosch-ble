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


ADDRESS_NAMES: dict[int, str] = {
    0x181E: "DRIVE_UNIT_PRESENT_ASSIST_FACTOR",
    0x182D: "DRIVE_UNIT_DISPLAYED_BIKE_SPEED",
    0x4081: "UI_PRIORITY",
    0x4082: "FEATURE_STREAMING_ALERT",
    0x4085: "ALTITUDE",
    0x4086: "MAXIMUM_ALTITUDE",
    0x4087: "ASCENT",
    0x4088: "DESCENT",
    0x4089: "STATE_OF_CHARGE",
    0x4094: "HEART_RATE",
    0x4095: "HEART_RATE_STATUS",
    0x4096: "NAVIGATION_CURRENT_STATUS",
    0x4097: "NAVIGATION_DISTANCE_TO_DESTINATION",
    0x4098: "NAVIGATION_ETA",
    0x4099: "NAVIGATION_TIME_TO_DESTINATION",
    0x409A: "ALTITUDE_GRAPH_AVAILABLE_SAMPLES",
    0x409F: "MOBILE_APP_FEATURE_PROPERTIES_RELEASE4",
    0x40A2: "SYSTEM_STATE_OF_CHARGE_FOR_RIDER_AT_DESTINATION",
    0x40A3: "PHONE_CHARGING",
    0x40A4: "USER_INFO",
    0x40A8: "SPEED",
    0x40A9: "STARTUP_STAGE",
    0xF809: "ASSIST_MODE_USAGE",
}


@dataclass(frozen=True)
class DirectedFrame:
    source: int
    destination: int
    message_type: MessageType
    sequence: int
    payload: bytes

    @property
    def target_name(self) -> str | None:
        return ADDRESS_NAMES.get(self.destination)


def _decode_address(high: int, low: int) -> int:
    return ((high & 0x7F) << 8) | low


def decode_directed_frame(data: bytes | str) -> DirectedFrame:
    if isinstance(data, str):
        data = bytes.fromhex(data)
    if len(data) < 5:
        raise ValueError("Directed frame is shorter than 5 bytes.")
    source = _decode_address(data[0], data[1])
    destination = _decode_address(data[2], data[3])
    type_and_sequence = data[4]
    return DirectedFrame(
        source=source,
        destination=destination,
        message_type=MessageType((type_and_sequence >> 4) & 0x0F),
        sequence=type_and_sequence & 0x0F,
        payload=data[5:],
    )
