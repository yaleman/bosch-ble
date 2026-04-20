from __future__ import annotations

from unittest.mock import patch

import pytest

from bosch_ble import dashboard, messagebus


def test_dashboard_state_updates_from_known_payloads() -> None:
    state = dashboard.DashboardState()

    state.apply_frame(messagebus.decode_directed_frame("2030c0a9210809"))
    state.apply_frame(messagebus.decode_directed_frame("2010c089a0084d"))
    state.apply_frame(messagebus.decode_directed_frame("2010c0a3a00801"))
    state.apply_frame(messagebus.decode_directed_frame("2010c0a8a008e613"))

    assert state.startup_stage == "STAGE9"
    assert state.battery_percent == 77
    assert state.charger_connected is True
    assert state.speed_kmh == pytest.approx(25.34)
    assert state.connection_status == "connected"


def test_dashboard_state_keeps_recent_frame_summaries_trimmed() -> None:
    state = dashboard.DashboardState(recent_limit=2)

    state.apply_frame(messagebus.decode_directed_frame("2030c0a9210809"))
    state.apply_frame(messagebus.decode_directed_frame("2150c09f01"))
    state.apply_frame(messagebus.decode_directed_frame("2002c08161"))

    assert list(state.recent_frames) == [
        "READ MOBILE_APP_FEATURE_PROPERTIES_RELEASE4",
        "SUBSCRIBE UI_PRIORITY",
    ]


def test_render_dashboard_shows_compact_interpreted_state() -> None:
    state = dashboard.DashboardState(
        connection_status="connected",
        startup_stage="STAGE9",
        assist_mode="Turbo",
        battery_percent=77,
        speed_kmh=25.34,
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
    assert "Assist     : Turbo" in rendered
    assert "Battery    : 77%" in rendered
    assert "Speed      : 25.34 km/h" in rendered
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
