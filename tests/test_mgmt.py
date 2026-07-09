from __future__ import annotations

import errno
import struct

import pytest

from bosch_ble import mgmt


def test_encode_load_connection_parameters_builds_expected_packet() -> None:
    packet = mgmt.encode_load_connection_parameters(
        mgmt.LoadConnectionParameters(
            address="00:04:63:BA:64:FC",
            controller_index=0,
            address_type=mgmt.LE_PUBLIC_ADDRESS,
            min_interval=24,
            max_interval=24,
            latency=0,
            timeout=72,
        )
    )

    assert packet == bytes.fromhex(
        "35 00 00 00 11 00 "
        "01 00 "
        "fc 64 ba 63 04 00 "
        "01 "
        "18 00 "
        "18 00 "
        "00 00 "
        "48 00"
    )


def test_parse_args_returns_load_connection_parameters() -> None:
    parsed = mgmt.parse_args(
        [
            "python",
            "load-conn-params",
            "--address",
            "AA:BB:CC:DD:EE:FF",
            "--controller-index",
            "1",
            "--address-type",
            "2",
            "--min-interval",
            "12",
            "--max-interval",
            "24",
            "--latency",
            "6",
            "--timeout",
            "200",
        ]
    )

    assert parsed == mgmt.LoadConnectionParameters(
        address="AA:BB:CC:DD:EE:FF",
        controller_index=1,
        address_type=2,
        min_interval=12,
        max_interval=24,
        latency=6,
        timeout=200,
    )


def test_parse_args_rejects_invalid_argv() -> None:
    with pytest.raises(SystemExit, match="Usage: python -m bosch_ble.mgmt load-conn-params"):
        mgmt.parse_args(["python"])


def test_receive_mgmt_response_parses_response_when_preceded_by_other_event() -> None:
    # An unrelated CMD_STATUS event (different opcode) arrives first in the same
    # datagram, followed by our CMD_COMPLETE for MGMT_OP_LOAD_CONN_PARAM.
    other_event = struct.pack("<HHH", mgmt.MGMT_EV_CMD_STATUS, 0, 3) + struct.pack(
        "<HB", 0x9999, mgmt.MGMT_STATUS_SUCCESS
    )
    our_event = struct.pack("<HHH", mgmt.MGMT_EV_CMD_COMPLETE, 0, 3) + struct.pack(
        "<HB", mgmt.MGMT_OP_LOAD_CONN_PARAM, mgmt.MGMT_STATUS_SUCCESS
    )
    buf = other_event + our_event

    class FakeSock:
        def __init__(self) -> None:
            self.calls = 0

        def recv(self, _n: int) -> bytes:
            self.calls += 1
            if self.calls == 1:
                return buf
            raise RuntimeError("recv exhausted before finding response")

    event_code, status = mgmt.receive_mgmt_response(FakeSock())

    assert event_code == mgmt.MGMT_EV_CMD_COMPLETE
    assert status == mgmt.MGMT_STATUS_SUCCESS


def test_receive_mgmt_response_handles_partial_event_across_recvs() -> None:
    our_event = struct.pack("<HHH", mgmt.MGMT_EV_CMD_COMPLETE, 0, 3) + struct.pack(
        "<HB", mgmt.MGMT_OP_LOAD_CONN_PARAM, mgmt.MGMT_STATUS_SUCCESS
    )

    class FakeSock:
        def __init__(self) -> None:
            self.calls = 0

        def recv(self, _n: int) -> bytes:
            self.calls += 1
            if self.calls == 1:
                return our_event[:4]
            if self.calls == 2:
                return our_event[4:]
            raise RuntimeError("recv exhausted")

    event_code, status = mgmt.receive_mgmt_response(FakeSock())

    assert event_code == mgmt.MGMT_EV_CMD_COMPLETE
    assert status == mgmt.MGMT_STATUS_SUCCESS



def test_load_connection_parameters_reports_trusted_socket_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSocket:
        def __enter__(self) -> FakeSocket:
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def settimeout(self, _timeout: float) -> None:
            return None

        def sendall(self, _packet: bytes) -> None:
            raise OSError(errno.ENOMEM, "Cannot allocate memory")

    monkeypatch.setattr(mgmt.socket, "socket", lambda *_args, **_kwargs: FakeSocket())
    monkeypatch.setattr(mgmt, "bind_mgmt_socket", lambda _sock: None)

    with pytest.raises(PermissionError, match="Trusted BlueZ mgmt socket required"):
        mgmt.load_connection_parameters(mgmt.LoadConnectionParameters(address="00:04:63:BA:64:FC"))
