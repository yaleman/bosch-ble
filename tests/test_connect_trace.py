from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import AsyncMock

import pytest

from bosch_ble import bluez, trace_connect


ADDRESS = "00:04:63:BA:64:FC"
GOOD_TRACE = """< HCI Command: LE Create Connection (0x08|0x000d) plen 25
        Peer address: 00:04:63:BA:64:FC (Bosch Security Systems)
        Min connection interval: 30.00 msec (0x0018)
        Max connection interval: 30.00 msec (0x0018)
        Connection latency: 0 (0x0000)
        Supervision timeout: 720 msec (0x0048)
> HCI Event: LE Meta Event (0x3e) plen 31
      LE Enhanced Connection Complete (0x0a)
        Handle: 46
        Peer address: 00:04:63:BA:64:FC (Bosch Security Systems)
< HCI Command: LE Connection Update (0x08|0x0013) plen 14
        Handle: 46
        Min connection interval: 20.00 msec (0x0010)
        Max connection interval: 40.00 msec (0x0020)
        Connection latency: 0 (0x0000)
        Supervision timeout: 4000 msec (0x0190)
bluetoothd[746]: < ACL Data TX: Handle 46 flags 0x00 dlen 7
      ATT: Exchange MTU Request (0x02) len 2
> ACL Data RX: Handle 46 flags 0x02 dlen 7
      ATT: Exchange MTU Response (0x03) len 2
"""


def summarize(text: str) -> bluez.PairAttemptSummary:
    return bluez.summarize_btmon_trace(
        text, pair_backend="connect", privacy="off", visible=True, name=None,
        assist_error=None, trace_path="btmon.log", address=ADDRESS,
    )


def bike_state(*, visible: bool = True) -> bluez.BluezState:
    return bluez.BluezState(
        address=ADDRESS, visible=visible, device=None, name="smart system eBike",
        paired=False, trusted=False, connected=True, services_resolved=True,
        bluetoothctl=CompletedProcess([], 0, stdout="", stderr=""), busctl=None,
        pairing_advertisement=True if visible else None,
    )


def test_initial_parameters_ignore_later_bike_requested_update() -> None:
    summary = summarize(GOOD_TRACE)
    assert summary.initial_parameters == (bluez.PHONE_LIKE_PARAMETERS,)
    assert summary.highest_stage is bluez.TraceStage.ATT
    assert summary.att_seen


def test_bad_initial_parameters_are_parsed_structurally() -> None:
    trace = GOOD_TRACE.replace("30.00 msec (0x0018)", "20.00 msec (0x0010)", 1)
    trace = trace.replace("30.00 msec (0x0018)", "40.00 msec (0x0020)", 1)
    trace = trace.replace("720 msec (0x0048)", "4000 msec (0x0190)", 1)
    assert summarize(trace).initial_parameters == (bluez.LeConnectionParameters(16, 32, 0, 400),)


def test_capability_names_do_not_count_as_connection_or_protocol_traffic() -> None:
    trace = """          LE Create Connection (Octet 26 - Bit 4)
          LE Read Remote Used Features (Octet 27 - Bit 5)
          LE Enhanced Connection Complete
          ATT supported
          SMP supported
"""
    summary = bluez.summarize_btmon_trace(
        trace, pair_backend="connect", privacy="off", visible=True, name=None,
        assist_error=None, trace_path="btmon.log",
    )
    assert summary.highest_stage is bluez.TraceStage.PRE_CONNECTION
    assert not summary.create_connection_seen
    assert not summary.enhanced_connection_complete_seen
    assert not summary.read_remote_features_seen
    assert not summary.att_seen
    assert not summary.smp_seen


def test_other_devices_att_is_excluded() -> None:
    trace = GOOD_TRACE.replace(ADDRESS, "AA:BB:CC:DD:EE:FF")
    summary = summarize(trace)
    assert summary.initial_parameters == ()
    assert summary.highest_stage is bluez.TraceStage.PRE_CONNECTION


def test_incomplete_parameters_are_unknown() -> None:
    trace = GOOD_TRACE.replace("        Connection latency: 0 (0x0000)\n", "")
    assert summarize(trace).initial_parameters == ()


def test_multiple_create_attempts_are_retained() -> None:
    assert summarize(GOOD_TRACE + GOOD_TRACE).initial_parameters == (
        bluez.PHONE_LIKE_PARAMETERS, bluez.PHONE_LIKE_PARAMETERS,
    )


@pytest.mark.parametrize("visible", [True, False])
def test_capture_gates_connect_and_writes_typed_outcome(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, visible: bool,
) -> None:
    state = bike_state(visible=visible)

    @asynccontextmanager
    async def fake_capture(*, path: Path):
        path.write_text(GOOD_TRACE if visible else "")
        yield path

    connect = AsyncMock(return_value=state)
    monkeypatch.setattr(bluez, "assert_controller_ready", lambda _address: None)
    monkeypatch.setattr(bluez, "btmon_text_capture", fake_capture)
    monkeypatch.setattr(bluez, "preflight_device", AsyncMock(return_value=state))
    monkeypatch.setattr(bluez, "connect_device", connect)
    monkeypatch.setattr(bluez, "wait_for_state", AsyncMock(return_value=state))
    monkeypatch.setattr(bluez, "read_device_state", lambda _address: state)
    monkeypatch.setattr(trace_connect.asyncio, "sleep", AsyncMock())
    outcome = asyncio.run(trace_connect.capture_connection(ADDRESS, tmp_path))
    expected = (trace_connect.ConnectOutcome.BASELINE_REACHED if visible
                else trace_connect.ConnectOutcome.BIKE_UNAVAILABLE)
    assert outcome is expected
    assert json.loads((tmp_path / "summary.json").read_text())["outcome"] == expected.value
    assert connect.await_count == int(visible)


def test_load_parameter_failure_stops_before_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bluez, "bluez_prepare_phone_like_pairing_controller", AsyncMock())
    monkeypatch.setattr(bluez, "bluez_set_pairable", AsyncMock(
        return_value=CompletedProcess([], 0, stdout="", stderr=""),
    ))
    monkeypatch.setattr(bluez, "refresh_visible_device", AsyncMock(return_value=bike_state()))
    monkeypatch.setattr(bluez, "bluez_load_connection_parameters", AsyncMock(
        return_value=CompletedProcess([], 1, stdout="", stderr="sudo: a password is required"),
    ))
    with pytest.raises(bluez.ConnectionSetupError) as exc:
        asyncio.run(bluez.prepare_connect_attempt(ADDRESS))
    assert exc.value.step is bluez.ConnectionSetupStep.PARAMETERS


def test_capture_waits_for_banner_and_uses_bounded_unprivileged_pty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    commands: list[tuple[str, ...]] = []

    class CaptureProcess:
        returncode: int | None = None

        def __init__(self) -> None:
            self.stdout = asyncio.StreamReader()
            self.stdout.feed_data(b"Bluetooth monitor ver 5.72\n")
            self.stdout.feed_eof()

        def terminate(self) -> None:
            self.returncode = 0

        def kill(self) -> None:
            self.returncode = -9

        async def wait(self) -> int:
            return self.returncode or 0

    async def spawn(*args: str, **kwargs: object) -> CaptureProcess:
        commands.append(args)
        return CaptureProcess()

    monkeypatch.setattr(bluez.asyncio, "create_subprocess_exec", spawn)
    path = tmp_path / "capture.log"

    async def run() -> None:
        async with bluez.btmon_text_capture(path=path):
            assert path.read_text() == "Bluetooth monitor ver 5.72\n"

    asyncio.run(run())
    assert commands == [(
        "timeout", "--signal=INT", "180s", "script", "--quiet", "--return",
        "--flush", "--command", "sudo -n btmon --no-pager --color never --columns 160",
        "/dev/null",
    )]
