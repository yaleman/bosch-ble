from __future__ import annotations

from pathlib import Path

import pytest

from bosch_ble import messagebus, validate_live


def test_decode_directed_frame_parses_startup_stage_write() -> None:
    frame = messagebus.decode_directed_frame(bytes.fromhex("2030c0a9210809"))

    assert frame.source == 0x2030
    assert frame.destination == 0x40A9
    assert frame.message_type is messagebus.MessageType.WRITE
    assert frame.sequence == 1
    assert frame.payload == bytes.fromhex("0809")
    assert frame.target_name == "STARTUP_STAGE"


def test_decode_directed_frame_parses_feature_properties_read() -> None:
    frame = messagebus.decode_directed_frame(bytes.fromhex("2150c09f01"))

    assert frame.source == 0x2150
    assert frame.destination == 0x409F
    assert frame.message_type is messagebus.MessageType.READ
    assert frame.sequence == 1
    assert frame.payload == b""
    assert frame.target_name == "MOBILE_APP_FEATURE_PROPERTIES_RELEASE4"


def test_decode_directed_frame_parses_visualizable_issue_types_read() -> None:
    frame = messagebus.decode_directed_frame(bytes.fromhex("2150c09d01"))

    assert frame.source == 0x2150
    assert frame.destination == 0x409D
    assert frame.message_type is messagebus.MessageType.READ
    assert frame.sequence == 1
    assert frame.payload == b""
    assert frame.target_name == "VISUALIZABLE_ISSUE_TYPES"


def test_decode_directed_frame_parses_update_issue_visualization_rpc() -> None:
    frame = messagebus.decode_directed_frame(bytes.fromhex("2150c09c41"))

    assert frame.source == 0x2150
    assert frame.destination == 0x409C
    assert frame.message_type is messagebus.MessageType.RPC
    assert frame.sequence == 1
    assert frame.payload == b""
    assert frame.target_name == "UPDATE_ISSUE_VISUALIZATION"


def test_decode_directed_frame_parses_get_altitude_graph_rpc() -> None:
    frame = messagebus.decode_directed_frame(bytes.fromhex("2150c09b41"))

    assert frame.source == 0x2150
    assert frame.destination == 0x409B
    assert frame.message_type is messagebus.MessageType.RPC
    assert frame.sequence == 1
    assert frame.payload == b""
    assert frame.target_name == "GET_ALTITUDE_GRAPH"


def test_decode_directed_frame_parses_mobile_app_subscribe() -> None:
    frame = messagebus.decode_directed_frame(bytes.fromhex("2002c0a460"))

    assert frame.source == 0x2002
    assert frame.destination == 0x40A4
    assert frame.message_type is messagebus.MessageType.SUBSCRIBE
    assert frame.sequence == 0
    assert frame.payload == b""
    assert frame.target_name == "USER_INFO"


def test_decode_directed_frame_parses_mobile_app_unsubscribe() -> None:
    frame = messagebus.decode_directed_frame(bytes.fromhex("2002c08184"))

    assert frame.source == 0x2002
    assert frame.destination == 0x4081
    assert frame.message_type is messagebus.MessageType.UNSUBSCRIBE
    assert frame.sequence == 4
    assert frame.payload == b""
    assert frame.target_name == "UI_PRIORITY"


def test_decode_message_frame_parses_notify() -> None:
    frame = messagebus.decode_message_frame("80bc084d")

    assert isinstance(frame, messagebus.NotifyFrame)
    assert frame.source == 0x00BC
    assert frame.payload == bytes.fromhex("084d")
    assert frame.source_name == "BATTERY_SYSTEM_STATE_OF_CHARGE_FOR_RIDER"


def test_decode_directed_frame_parses_success_response_without_status_byte() -> None:
    frame = messagebus.decode_directed_frame("409fa150110801")

    assert frame.source == 0x409F
    assert frame.destination == 0x2150
    assert frame.message_type is messagebus.MessageType.READ_RESPONSE
    assert frame.sequence == 1
    assert frame.status_code is messagebus.ResponseStatusCode.SUCCESS
    assert frame.payload == bytes.fromhex("0801")


def test_decode_directed_frame_parses_error_response_with_status_byte() -> None:
    frame = messagebus.decode_directed_frame("40ff20027104")

    assert frame.source == 0x40FF
    assert frame.destination == 0x2002
    assert frame.message_type is messagebus.MessageType.SUBSCRIBE_RESPONSE
    assert frame.sequence == 1
    assert frame.status_code is messagebus.ResponseStatusCode.UNSUPPORTED
    assert frame.payload == b""


def test_encode_read_response_matches_android_wire_shape() -> None:
    request = messagebus.decode_directed_frame("2150c09f01")

    encoded = messagebus.encode_read_response(request, bytes.fromhex("0801"))

    assert encoded.hex() == "409fa150110801"


def test_encode_read_response_matches_visualizable_issue_types_wire_shape() -> None:
    request = messagebus.decode_directed_frame("2150c09d01")

    encoded = messagebus.encode_read_response(request, bytes.fromhex("0800080108020803"))

    assert encoded.hex() == "409da150110800080108020803"


def test_encode_subscribe_response_and_notify_match_android_wire_shape() -> None:
    request = messagebus.decode_directed_frame("2002c0a360")

    response = messagebus.encode_subscribe_response(request)
    notify = messagebus.encode_notify(0x40A3, b"")

    assert response.hex() == "40a3a00270"
    assert notify.hex() == "c0a3"


def test_encode_rpc_response_matches_empty_success_wire_shape() -> None:
    request = messagebus.decode_directed_frame("2150c09c41")

    encoded = messagebus.encode_rpc_response(request)

    assert encoded.hex() == "409ca15051"


def test_encode_read_response_matches_location_wire_shape() -> None:
    request = messagebus.decode_directed_frame("2150c0a001")

    encoded = messagebus.encode_read_response(request, b"")

    assert encoded.hex() == "40a0a15011"


def test_encode_subscribe_response_and_notify_match_navigation_advice_wire_shape() -> None:
    request = messagebus.decode_directed_frame("2002c0a160")

    response = messagebus.encode_subscribe_response(request)
    notify = messagebus.encode_notify(0x40A1, b"")

    assert response.hex() == "40a1a00270"
    assert notify.hex() == "c0a1"


def test_encode_rpc_response_matches_get_altitude_graph_wire_shape() -> None:
    request = messagebus.decode_directed_frame("2150c09b41")

    encoded = messagebus.encode_rpc_response(request)

    assert encoded.hex() == "409ba15051"


def test_encode_unsubscribe_response_matches_wire_shape() -> None:
    request = messagebus.decode_directed_frame("2002c08184")

    encoded = messagebus.encode_unsubscribe_response(request)

    assert encoded.hex() == "4081a00294"


def test_validate_handshake_log_accepts_known_startup_burst() -> None:
    log_text = """\
2026-04-20T15:09:14 RECV command=VersionCommand(version=3)
2026-04-20T15:09:14 RECV command=MaxSegmentationPacketCommand(max_packet_size=244)
2026-04-20T15:09:14 RECV command=AdvanceTransmitWindowCommand(channel=<McspChannel.CHANNEL1: 1>, advance=2048)
2026-04-20T15:09:14 RECV command=AdvanceTransmitWindowCommand(channel=<McspChannel.CHANNEL2: 2>, advance=8192)
2026-04-20T15:09:14 RECV command=AdvanceTransmitWindowCommand(channel=<McspChannel.CHANNEL3: 3>, advance=8192)
2026-04-20T15:09:14 RECV command=AdvanceTransmitWindowCommand(channel=<McspChannel.CHANNEL4: 4>, advance=0)
2026-04-20T15:09:14 RECV command=AdvanceTransmitWindowCommand(channel=<McspChannel.CHANNEL5: 5>, advance=0)
2026-04-20T15:09:14 RECV command=AdvanceTransmitWindowCommand(channel=<McspChannel.CHANNEL6: 6>, advance=0)
2026-04-20T15:09:14 RECV command=AdvanceTransmitWindowCommand(channel=<McspChannel.CHANNEL7: 7>, advance=0)
2026-04-20T15:09:14 SEND hex=10020103
2026-04-20T15:09:14 SEND hex=10030400f4
2026-04-20T15:09:14 SEND hex=10020301
2026-04-20T15:09:14 SEND hex=10020302
2026-04-20T15:09:14 SEND hex=10020303
2026-04-20T15:09:14 SEND hex=10020304
2026-04-20T15:09:14 SEND hex=10020305
2026-04-20T15:09:14 SEND hex=10020306
2026-04-20T15:09:14 SEND hex=10020307
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2030c0a9210809
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2150c09f01
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c08161
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c08561
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c0a861
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2100c09501
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c09560
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c09460
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2100c09f01
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c08260
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c08660
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c08760
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c08860
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c08960
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c09660
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c09760
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c09860
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c09960
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c09a60
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c0a260
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c0a360
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c0a460
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2010c08101
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2100c09f02
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2150c09f02
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2030c0a9220809
2026-04-20T15:09:15 FRAME channel=CHANNEL1 end=True hex=2010c08102
2026-04-20T15:09:15 FRAME channel=CHANNEL1 end=True hex=2150c09f03
"""

    result = validate_live.validate_handshake_log(log_text)

    assert result.passed is True
    assert result.missing == []
    assert result.missing_mcsp == []
    assert result.missing_send == []
    assert result.decoded["2030c0a9210809"].target_name == "STARTUP_STAGE"
    assert result.decoded["2150c09f01"].target_name == "MOBILE_APP_FEATURE_PROPERTIES_RELEASE4"
    assert result.decoded["2002c0a460"].target_name == "USER_INFO"


def test_validate_handshake_log_ignores_notify_frames_on_channel1() -> None:
    log_text = """\
2026-04-20T15:09:14 RECV command=VersionCommand(version=3)
2026-04-20T15:09:14 RECV command=MaxSegmentationPacketCommand(max_packet_size=244)
2026-04-20T15:09:14 RECV command=AdvanceTransmitWindowCommand(channel=<McspChannel.CHANNEL1: 1>, advance=2048)
2026-04-20T15:09:14 RECV command=AdvanceTransmitWindowCommand(channel=<McspChannel.CHANNEL2: 2>, advance=8192)
2026-04-20T15:09:14 RECV command=AdvanceTransmitWindowCommand(channel=<McspChannel.CHANNEL3: 3>, advance=8192)
2026-04-20T15:09:14 RECV command=AdvanceTransmitWindowCommand(channel=<McspChannel.CHANNEL4: 4>, advance=0)
2026-04-20T15:09:14 RECV command=AdvanceTransmitWindowCommand(channel=<McspChannel.CHANNEL5: 5>, advance=0)
2026-04-20T15:09:14 RECV command=AdvanceTransmitWindowCommand(channel=<McspChannel.CHANNEL6: 6>, advance=0)
2026-04-20T15:09:14 RECV command=AdvanceTransmitWindowCommand(channel=<McspChannel.CHANNEL7: 7>, advance=0)
2026-04-20T15:09:14 SEND hex=10020103
2026-04-20T15:09:14 SEND hex=10030400f4
2026-04-20T15:09:14 SEND hex=10020301
2026-04-20T15:09:14 SEND hex=10020302
2026-04-20T15:09:14 SEND hex=10020303
2026-04-20T15:09:14 SEND hex=10020304
2026-04-20T15:09:14 SEND hex=10020305
2026-04-20T15:09:14 SEND hex=10020306
2026-04-20T15:09:14 SEND hex=10020307
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=80bc084d
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2030c0a9210809
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2030c0a9220809
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2150c09f01
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2100c09f01
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2100c09f02
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2150c09f02
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2150c09f03
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c08161
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c09560
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c0a360
2026-04-20T15:09:14 FRAME channel=CHANNEL1 end=True hex=2002c0a460
"""

    result = validate_live.validate_handshake_log(log_text)

    assert result.passed is True
    assert "80bc084d" not in result.decoded


def test_validate_handshake_log_reports_missing_expectations() -> None:
    result = validate_live.validate_handshake_log("2026-04-20T15:09:14 SEND hex=10020103\n")

    assert result.passed is False
    assert "2030c0a9210809" in result.missing
    assert "VersionCommand(version=3)" in result.missing_mcsp
    assert "10030400f4" in result.missing_send


def test_validate_live_cli_reads_log_file_and_prints_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    log_path = tmp_path / "handshake.log"
    log_path.write_text(
        "2026-04-20T15:09:14 RECV command=VersionCommand(version=3)\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit) as excinfo:
        validate_live.cli(["bosch-ble-validate-live", str(log_path)])

    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "Validation failed" in captured.err
