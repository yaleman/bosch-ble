from __future__ import annotations

import asyncio
from subprocess import CompletedProcess
from unittest.mock import AsyncMock, patch

import pytest

from bosch_ble import bluez, dashboard, messagebus


def test_dashboard_state_updates_from_known_payloads() -> None:
    state = dashboard.DashboardState()

    state.apply_message(messagebus.decode_directed_frame("2030c0a9210809"))
    state.apply_message(messagebus.decode_message_frame("80bc084d"))
    state.apply_message(messagebus.decode_message_frame("808a0801"))
    state.apply_message(messagebus.decode_message_frame("982d08191001"))
    state.apply_message(messagebus.decode_message_frame("981e08d402"))

    assert state.startup_stage == "STAGE9"
    assert state.battery_percent == 77
    assert state.charger_connected is True
    assert state.speed_raw == 25
    assert state.assist_mode == "340"
    assert state.connection_status == "connected"


def test_dashboard_state_keeps_recent_frame_summaries_trimmed() -> None:
    state = dashboard.DashboardState(recent_limit=2)

    state.apply_message(messagebus.decode_directed_frame("2030c0a9210809"))
    state.apply_message(messagebus.decode_directed_frame("2150c09f01"))
    state.apply_message(messagebus.decode_message_frame("80bc084d"))

    assert list(state.recent_frames) == [
        "READ MOBILE_APP_FEATURE_PROPERTIES_RELEASE4",
        "NOTIFY BATTERY_SYSTEM_STATE_OF_CHARGE_FOR_RIDER payload=084d",
    ]


def test_render_dashboard_shows_compact_interpreted_state() -> None:
    state = dashboard.DashboardState(
        connection_status="connected",
        startup_stage="STAGE9",
        assist_mode="340",
        battery_percent=77,
        speed_raw=25,
        charger_connected=False,
        recent_limit=3,
    )
    state.recent_frames.extend(
        [
            "WRITE STARTUP_STAGE payload=0809",
            "NOTIFY STATE_OF_CHARGE payload=084d",
        ]
    )

    rendered = dashboard.render_dashboard(state)

    assert "Connection : connected" in rendered
    assert "Startup    : STAGE9" in rendered
    assert "Assist     : 340" in rendered
    assert "Battery    : 77%" in rendered
    assert "Speed      : 25 raw" in rendered
    assert "Charger    : unplugged" in rendered
    assert "Recent frames:" in rendered
    assert "WRITE STARTUP_STAGE payload=0809" in rendered


def test_dashboard_cli_shows_usage_without_address(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("sys.argv", ["bosch-ble-dashboard"]):
        with pytest.raises(SystemExit) as excinfo:
            dashboard.cli()

    assert excinfo.value.code == 2
    assert "Usage: bosch-ble-dashboard <BLE_ADDRESS>" in capsys.readouterr().out


def test_dashboard_cli_runs_async_main_with_address() -> None:
    async def fake_main(address: str) -> None:
        assert address == "AA:BB"

    with patch.object(dashboard, "main", side_effect=fake_main) as patched_main:
        with patch("sys.argv", ["bosch-ble-dashboard", "AA:BB"]):
            dashboard.cli()

    patched_main.assert_called_once_with("AA:BB")


def test_dashboard_cli_prints_friendly_error(capsys: pytest.CaptureFixture[str]) -> None:
    async def fake_main(address: str) -> None:
        raise RuntimeError(f"bad dashboard for {address}")

    with patch.object(dashboard, "main", side_effect=fake_main):
        with patch("sys.argv", ["bosch-ble-dashboard", "AA:BB"]):
            with pytest.raises(SystemExit) as excinfo:
                dashboard.cli()

    assert excinfo.value.code == 1
    assert capsys.readouterr().err == "Error: bad dashboard for AA:BB\n"


def test_dashboard_can_render_unknown_state() -> None:
    rendered = dashboard.render_dashboard(dashboard.DashboardState())

    assert "Assist     : unknown" in rendered
    assert "Battery    : unknown" in rendered
    assert "Speed      : unknown" in rendered
    assert "Charger    : unknown" in rendered


def test_dashboard_main_serializes_startup_responses_after_handshake_packets(
    tmp_path,
) -> None:
    receive_uuid = "00000011-eaa2-11e9-81b4-2a2ae2dbcce4"
    send_uuid = "00000012-eaa2-11e9-81b4-2a2ae2dbcce4"

    class FakeCharacteristic:
        def __init__(self, uuid: str, properties: list[str]) -> None:
            self.uuid = uuid
            self.properties = properties

    class FakeService:
        def __init__(self, uuid: str, characteristics: list[FakeCharacteristic]) -> None:
            self.uuid = uuid
            self.characteristics = characteristics

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
        with patch.object(dashboard.live.dump_gatt, "prepare_connection", new=AsyncMock(return_value=state)):
            with patch.object(dashboard.live.dump_gatt, "client_target_for_state", return_value=object()):
                with patch.object(dashboard.live, "BleakClient", FakeClient):
                    stop = asyncio.Event()
                    stop.set()
                    with patch("bosch_ble.dashboard.asyncio.Event", return_value=stop):
                        await dashboard.main("AA:BB")

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
