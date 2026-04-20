from __future__ import annotations

import asyncio
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import AsyncMock, patch

from bosch_ble import bluez, handshake, mcsp


class FakeCharacteristic:
    def __init__(self, uuid: str, properties: list[str]) -> None:
        self.uuid = uuid
        self.properties = properties
        self.descriptors: list[object] = []
        self.description = uuid


class FakeService:
    def __init__(self, uuid: str, characteristics: list[FakeCharacteristic]) -> None:
        self.uuid = uuid
        self.characteristics = characteristics
        self.description = uuid


def test_decode_command_frames_parses_bike_handshake_snapshot() -> None:
    payload = bytes.fromhex(
        "10020103"
        "10030400f4"
        "1006020100000800"
        "1006020200002000"
        "1006020300002000"
        "1006020400000000"
        "1006020500000000"
        "1006020600000000"
        "1006020700000000"
    )

    commands = mcsp.decode_command_frames(payload)

    assert commands == [
        mcsp.VersionCommand(version=3),
        mcsp.MaxSegmentationPacketCommand(max_packet_size=244),
        mcsp.AdvanceTransmitWindowCommand(channel=mcsp.McspChannel.CHANNEL1, advance=2048),
        mcsp.AdvanceTransmitWindowCommand(channel=mcsp.McspChannel.CHANNEL2, advance=8192),
        mcsp.AdvanceTransmitWindowCommand(channel=mcsp.McspChannel.CHANNEL3, advance=8192),
        mcsp.AdvanceTransmitWindowCommand(channel=mcsp.McspChannel.CHANNEL4, advance=0),
        mcsp.AdvanceTransmitWindowCommand(channel=mcsp.McspChannel.CHANNEL5, advance=0),
        mcsp.AdvanceTransmitWindowCommand(channel=mcsp.McspChannel.CHANNEL6, advance=0),
        mcsp.AdvanceTransmitWindowCommand(channel=mcsp.McspChannel.CHANNEL7, advance=0),
    ]


def test_build_handshake_response_matches_android_startup_sequence() -> None:
    commands = mcsp.decode_command_frames(
        bytes.fromhex(
            "10020103"
            "10030400f4"
            "1006020100000800"
            "1006020200002000"
            "1006020300002000"
            "1006020400000000"
            "1006020500000000"
            "1006020600000000"
            "1006020700000000"
        )
    )

    response = handshake.build_handshake_response(commands, local_packet_size=244)

    assert [frame.hex() for frame in response] == [
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


def test_handshake_main_replies_on_mcsp_transport(
    tmp_path: Path,
    capsys,
) -> None:
    targets: list[object] = []
    writes: list[tuple[str, bytes, bool]] = []
    target = object()
    receive_uuid = "00000011-eaa2-11e9-81b4-2a2ae2dbcce4"
    send_uuid = "00000012-eaa2-11e9-81b4-2a2ae2dbcce4"
    services = [
        FakeService(
            "00000010-eaa2-11e9-81b4-2a2ae2dbcce4",
            [
                FakeCharacteristic(receive_uuid, ["notify"]),
                FakeCharacteristic(send_uuid, ["write-without-response"]),
            ],
        )
    ]

    class FakeClient:
        def __init__(self, address_or_ble_device, timeout: float = 20.0) -> None:
            targets.append(address_or_ble_device)
            self.address_or_ble_device = address_or_ble_device
            self.timeout = timeout
            self.is_connected = True
            self.services = services

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def start_notify(self, uuid: str, callback) -> None:
            callback(
                "notify-sender",
                bytearray.fromhex(
                    "10020103"
                    "10030400f4"
                    "1006020100000800"
                    "1006020200002000"
                    "1006020300002000"
                    "1006020400000000"
                    "1006020500000000"
                    "1006020600000000"
                    "1006020700000000"
                ),
            )

        async def stop_notify(self, uuid: str) -> None:
            return None

        async def write_gatt_char(self, uuid: str, data: bytes, response: bool = False) -> None:
            writes.append((uuid, data, response))

    async def run() -> None:
        state = bluez.BluezState(
            address="AA:BB",
            visible=False,
            device=None,
            name="sensor",
            paired=True,
            trusted=True,
            connected=True,
            services_resolved=True,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
        )
        with patch.object(handshake.live.dump_gatt, "prepare_connection", new=AsyncMock(return_value=state)):
            with patch.object(handshake.live.dump_gatt, "client_target_for_state", return_value=target):
                with patch.object(handshake.live, "BleakClient", FakeClient):
                    await handshake.main("AA:BB", str(tmp_path / "handshake.log"))

    asyncio.run(run())

    assert targets == [target]
    assert writes == [
        (send_uuid, bytes.fromhex("10020103"), False),
        (send_uuid, bytes.fromhex("10030400f4"), False),
        (send_uuid, bytes.fromhex("10020301"), False),
        (send_uuid, bytes.fromhex("10020302"), False),
        (send_uuid, bytes.fromhex("10020303"), False),
        (send_uuid, bytes.fromhex("10020304"), False),
        (send_uuid, bytes.fromhex("10020305"), False),
        (send_uuid, bytes.fromhex("10020306"), False),
        (send_uuid, bytes.fromhex("10020307"), False),
    ]
    output = capsys.readouterr().out
    assert "Connecting to AA:BB ..." in output
    assert "RECV command=VersionCommand(version=3)" in output
    assert "SEND hex=10020307" in output


def test_handshake_main_logs_non_command_frames_after_handshake(
    tmp_path: Path,
    capsys,
) -> None:
    receive_uuid = "00000011-eaa2-11e9-81b4-2a2ae2dbcce4"
    send_uuid = "00000012-eaa2-11e9-81b4-2a2ae2dbcce4"
    services = [
        FakeService(
            "00000010-eaa2-11e9-81b4-2a2ae2dbcce4",
            [
                FakeCharacteristic(receive_uuid, ["notify"]),
                FakeCharacteristic(send_uuid, ["write-without-response"]),
            ],
        )
    ]

    class FakeClient:
        def __init__(self, address_or_ble_device, timeout: float = 20.0) -> None:
            self.address_or_ble_device = address_or_ble_device
            self.timeout = timeout
            self.is_connected = True
            self.services = services

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def start_notify(self, uuid: str, callback) -> None:
            callback(
                "notify-sender",
                bytearray.fromhex(
                    "10020103"
                    "10030400f4"
                    "1006020100000800"
                    "1006020200002000"
                    "1006020300002000"
                    "1006020400000000"
                    "1006020500000000"
                    "1006020600000000"
                    "1006020700000000"
                ),
            )
            callback("notify-sender", bytearray.fromhex("30052002c08161"))

        async def stop_notify(self, uuid: str) -> None:
            return None

        async def write_gatt_char(self, uuid: str, data: bytes, response: bool = False) -> None:
            return None

    async def run() -> None:
        state = bluez.BluezState(
            address="AA:BB",
            visible=False,
            device=None,
            name="sensor",
            paired=True,
            trusted=True,
            connected=True,
            services_resolved=True,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
        )
        with patch.object(handshake.live.dump_gatt, "prepare_connection", new=AsyncMock(return_value=state)):
            with patch.object(handshake.live.dump_gatt, "client_target_for_state", return_value=object()):
                with patch.object(handshake.live, "BleakClient", FakeClient):
                    await handshake.main("AA:BB", str(tmp_path / "handshake.log"))

    asyncio.run(run())

    output = capsys.readouterr().out
    assert "FRAME channel=CHANNEL1 end=True hex=2002c08161" in output
    assert "DECODE_FAILED" not in output


def test_handshake_main_serializes_startup_responses_after_handshake_packets(
    tmp_path: Path,
) -> None:
    receive_uuid = "00000011-eaa2-11e9-81b4-2a2ae2dbcce4"
    send_uuid = "00000012-eaa2-11e9-81b4-2a2ae2dbcce4"
    services = [
        FakeService(
            "00000010-eaa2-11e9-81b4-2a2ae2dbcce4",
            [
                FakeCharacteristic(receive_uuid, ["notify"]),
                FakeCharacteristic(send_uuid, ["write-without-response"]),
            ],
        )
    ]
    writes: list[tuple[str, bytes, bool]] = []

    class FakeClient:
        def __init__(self, address_or_ble_device, timeout: float = 20.0) -> None:
            self.address_or_ble_device = address_or_ble_device
            self.timeout = timeout
            self.is_connected = True
            self.services = services
            self._callback = None
            self._injected = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def start_notify(self, uuid: str, callback) -> None:
            self._callback = callback
            callback(
                "notify-sender",
                bytearray.fromhex(
                    "10020103"
                    "10030400f4"
                    "1006020100000800"
                    "1006020200002000"
                    "1006020300002000"
                    "1006020400000000"
                    "1006020500000000"
                    "1006020600000000"
                    "1006020700000000"
                ),
            )

        async def stop_notify(self, uuid: str) -> None:
            return None

        async def write_gatt_char(self, uuid: str, data: bytes, response: bool = False) -> None:
            writes.append((uuid, data, response))
            if not self._injected and self._callback is not None:
                self._injected = True
                self._callback("notify-sender", bytearray.fromhex("30052002c08161"))
                await asyncio.sleep(0)

    async def run() -> None:
        state = bluez.BluezState(
            address="AA:BB",
            visible=False,
            device=None,
            name="sensor",
            paired=True,
            trusted=True,
            connected=True,
            services_resolved=True,
            bluetoothctl=CompletedProcess(["bluetoothctl"], 0, stdout="", stderr=""),
            busctl=CompletedProcess(["busctl"], 0, stdout="", stderr=""),
        )
        with patch.object(handshake.live.dump_gatt, "prepare_connection", new=AsyncMock(return_value=state)):
            with patch.object(handshake.live.dump_gatt, "client_target_for_state", return_value=object()):
                with patch.object(handshake.live, "BleakClient", FakeClient):
                    await handshake.main("AA:BB", str(tmp_path / "handshake.log"))

    asyncio.run(run())

    assert [data.hex() for _, data, _ in writes] == [
        "10020103",
        "10030400f4",
        "10020301",
        "10020302",
        "10020303",
        "10020304",
        "10020305",
        "10020306",
        "10020307",
        "30054081a00271",
        "3004c0810824",
    ]


def test_build_startup_response_packets_answers_reads_and_subscribes() -> None:
    read_packets = handshake.build_startup_response_packets(
        messagebus=mcsp.encode_frame(
            mcsp.Frame(
                end_of_channel=True,
                channel=mcsp.McspChannel.CHANNEL1,
                payload=bytes.fromhex("2150c09f01"),
            )
        )
    )
    subscribe_packets = handshake.build_startup_response_packets(
        messagebus=mcsp.encode_frame(
            mcsp.Frame(
                end_of_channel=True,
                channel=mcsp.McspChannel.CHANNEL1,
                payload=bytes.fromhex("2002c0a360"),
            )
        )
    )

    assert [packet.hex() for packet in read_packets] == ["3007409fa150110801"]
    assert [packet.hex() for packet in subscribe_packets] == [
        "300540a3a00270",
        "3002c0a3",
    ]


def test_build_startup_response_packets_answers_visualizable_issue_types() -> None:
    packets = handshake.build_startup_response_packets(
        messagebus=mcsp.encode_frame(
            mcsp.Frame(
                end_of_channel=True,
                channel=mcsp.McspChannel.CHANNEL1,
                payload=bytes.fromhex("2150c09d01"),
            )
        )
    )

    assert [packet.hex() for packet in packets] == ["300d409da150110800080108020803"]


def test_build_startup_response_packets_answers_unsubscribes() -> None:
    packets = handshake.build_startup_response_packets(
        messagebus=mcsp.encode_frame(
            mcsp.Frame(
                end_of_channel=True,
                channel=mcsp.McspChannel.CHANNEL1,
                payload=bytes.fromhex("2002c08184"),
            )
        )
    )

    assert [packet.hex() for packet in packets] == ["30054081a00294"]


def test_build_startup_response_packets_answers_update_issue_visualization_rpc() -> None:
    packets = handshake.build_startup_response_packets(
        messagebus=mcsp.encode_frame(
            mcsp.Frame(
                end_of_channel=True,
                channel=mcsp.McspChannel.CHANNEL1,
                payload=bytes.fromhex("2150c09c41"),
            )
        )
    )

    assert [packet.hex() for packet in packets] == ["3005409ca15051"]


def test_build_startup_response_packets_answers_location_read() -> None:
    packets = handshake.build_startup_response_packets(
        messagebus=mcsp.encode_frame(
            mcsp.Frame(
                end_of_channel=True,
                channel=mcsp.McspChannel.CHANNEL1,
                payload=bytes.fromhex("2150c0a001"),
            )
        )
    )

    assert [packet.hex() for packet in packets] == ["300540a0a15011"]


def test_build_startup_response_packets_answers_navigation_advice_subscribe() -> None:
    packets = handshake.build_startup_response_packets(
        messagebus=mcsp.encode_frame(
            mcsp.Frame(
                end_of_channel=True,
                channel=mcsp.McspChannel.CHANNEL1,
                payload=bytes.fromhex("2002c0a160"),
            )
        )
    )

    assert [packet.hex() for packet in packets] == [
        "300540a1a00270",
        "3002c0a1",
    ]


def test_build_startup_response_packets_answers_get_altitude_graph_rpc() -> None:
    packets = handshake.build_startup_response_packets(
        messagebus=mcsp.encode_frame(
            mcsp.Frame(
                end_of_channel=True,
                channel=mcsp.McspChannel.CHANNEL1,
                payload=bytes.fromhex("2150c09b41"),
            )
        )
    )

    assert [packet.hex() for packet in packets] == ["3005409ba15051"]


def test_build_startup_response_packets_returns_unsupported_for_unmapped_request() -> None:
    packets = handshake.build_startup_response_packets(
        messagebus=mcsp.encode_frame(
            mcsp.Frame(
                end_of_channel=True,
                channel=mcsp.McspChannel.CHANNEL1,
                payload=bytes.fromhex("2002c0ff61"),
            )
        )
    )

    assert [packet.hex() for packet in packets] == ["300640ff20027104"]
