from __future__ import annotations

from bosch_ble import log_chars, mcsp
from bosch_ble._common import BleakDescriptor


class FakeChar:
    def __init__(self, uuid: str, properties: list[str]) -> None:
        self.uuid = uuid
        self.properties = properties
        self.descriptors: list[BleakDescriptor] = []


class FakeService:
    def __init__(self, uuid: str, characteristics: list[FakeChar]) -> None:
        self.uuid = uuid
        self.characteristics = characteristics


def test_collect_log_characteristics_skips_mcsp_transport() -> None:
    services = [
        FakeService(
            mcsp.MCSP_SERVICE_UUID,
            [
                FakeChar(mcsp.MCSP_RECEIVE_UUID, ["notify"]),
                FakeChar(mcsp.MCSP_SEND_UUID, ["write-without-response"]),
            ],
        ),
        FakeService(
            "0000180f-eaa2-11e9-81b4-2a2ae2dbcce4",
            [
                FakeChar("aaaa", ["notify", "read"]),
                FakeChar("bbbb", ["read"]),
                FakeChar("cccc", ["write"]),
            ],
        ),
    ]

    notify, read = log_chars.collect_log_characteristics(services)

    assert notify == ["aaaa"]
    assert read == ["aaaa", "bbbb"]
