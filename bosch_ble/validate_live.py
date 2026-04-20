from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

from bosch_ble import messagebus


MCSP_EXPECTATIONS = [
    "VersionCommand(version=3)",
    "MaxSegmentationPacketCommand(max_packet_size=244)",
    "AdvanceTransmitWindowCommand(channel=<McspChannel.CHANNEL1: 1>, advance=2048)",
    "AdvanceTransmitWindowCommand(channel=<McspChannel.CHANNEL2: 2>, advance=8192)",
    "AdvanceTransmitWindowCommand(channel=<McspChannel.CHANNEL3: 3>, advance=8192)",
    "AdvanceTransmitWindowCommand(channel=<McspChannel.CHANNEL4: 4>, advance=0)",
    "AdvanceTransmitWindowCommand(channel=<McspChannel.CHANNEL5: 5>, advance=0)",
    "AdvanceTransmitWindowCommand(channel=<McspChannel.CHANNEL6: 6>, advance=0)",
    "AdvanceTransmitWindowCommand(channel=<McspChannel.CHANNEL7: 7>, advance=0)",
]

SEND_EXPECTATIONS = [
    "10020103",
    "10030400f4",
    "10020301",
    "10020302",
    "10020303",
    "10020304",
    "10020305",
    "10020306",
    "10020307",
]

FRAME_EXPECTATIONS = [
    "2030c0a9210809",
    "2030c0a9220809",
    "2150c09f01",
    "2100c09f01",
    "2100c09f02",
    "2150c09f02",
    "2150c09f03",
    "2002c08161",
    "2002c09560",
    "2002c0a360",
    "2002c0a460",
]

FRAME_GROUP_EXPECTATIONS: dict[str, tuple[str, ...]] = {
    "UI_PRIORITY subscribe sweep": ("2002c08160", "2002c08161", "2002c08162"),
    "HEART_RATE_STATUS subscribe sweep": ("2002c09560", "2002c09561", "2002c09562"),
    "PHONE_CHARGING subscribe sweep": ("2002c0a360", "2002c0a361", "2002c0a362"),
    "USER_INFO subscribe sweep": ("2002c0a460", "2002c0a461", "2002c0a462"),
}

CHANNEL1_PATTERN = re.compile(r"FRAME channel=CHANNEL1 end=True hex=([0-9a-f]+)", re.IGNORECASE)


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    missing: list[str]
    missing_mcsp: list[str]
    missing_send: list[str]
    decoded: dict[str, messagebus.DirectedFrame]


def validate_handshake_log(text: str) -> ValidationResult:
    lower_text = text.lower()
    missing_mcsp = [entry for entry in MCSP_EXPECTATIONS if entry not in text]
    missing_send = [entry for entry in SEND_EXPECTATIONS if f"send hex={entry}" not in lower_text]

    decoded: dict[str, messagebus.DirectedFrame] = {}
    frame_hexes: set[str] = set()
    for match in CHANNEL1_PATTERN.finditer(text):
        frame_hex = match.group(1).lower()
        frame_hexes.add(frame_hex)
        decoded[frame_hex] = messagebus.decode_directed_frame(frame_hex)

    missing = [frame_hex for frame_hex in FRAME_EXPECTATIONS if frame_hex not in frame_hexes]
    for label, options in FRAME_GROUP_EXPECTATIONS.items():
        if not any(option in frame_hexes for option in options):
            missing.append(label)
    return ValidationResult(
        passed=not (missing or missing_mcsp or missing_send),
        missing=missing,
        missing_mcsp=missing_mcsp,
        missing_send=missing_send,
        decoded=decoded,
    )


def _format_failures(items: list[str]) -> str:
    return ", ".join(items) if items else "none"


def cli(argv: list[str] | None = None) -> None:
    argv = argv or sys.argv
    if len(argv) != 2:
        print(f"Usage: {argv[0]} <handshake_log>", file=sys.stdout)
        raise SystemExit(2)

    path = Path(argv[1])
    result = validate_handshake_log(path.read_text(encoding="utf-8"))
    if result.passed:
        print(f"Validation passed for {path}")
        print(f"Decoded {len(result.decoded)} CHANNEL1 frames")
        return

    print(f"Validation failed for {path}", file=sys.stderr)
    print(f"Missing MCSP expectations: {_format_failures(result.missing_mcsp)}", file=sys.stderr)
    print(f"Missing send expectations: {_format_failures(result.missing_send)}", file=sys.stderr)
    print(f"Missing frame expectations: {_format_failures(result.missing)}", file=sys.stderr)
    raise SystemExit(1)
