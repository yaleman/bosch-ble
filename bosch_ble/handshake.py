#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path

from bosch_ble import live, mcsp, messagebus as messagebus_mod
from bosch_ble._common import format_cli_error, ts, validate_address


HANDSHAKE_TIMEOUT_SECONDS = 10.0
POST_HANDSHAKE_WAIT_SECONDS = 1.0
STARTUP_WRITE_ADDRESSES = {0x40A9}
STARTUP_RPC_ADDRESSES = {0x409B, 0x409C}


find_mcsp_transport = live.find_mcsp_transport
is_bike_handshake = live.is_bike_handshake
build_handshake_response = live.build_handshake_response


def build_startup_response_packets(
    *,
    frame: mcsp.Frame,
    decoded: messagebus_mod.MessageFrame | None = None,
) -> list[bytes]:
    if frame.channel is mcsp.McspChannel.COMMAND:
        return []

    if decoded is None:
        decoded = messagebus_mod.decode_message_frame(frame.payload)
    if not isinstance(decoded, messagebus_mod.DirectedFrame):
        return []

    responses: list[bytes] = []
    payload = messagebus_mod.STARTUP_PROVIDER_PAYLOADS.get(decoded.destination)
    if decoded.message_type is messagebus_mod.MessageType.READ:
        if payload is None:
            responses.append(
                messagebus_mod.encode_read_response(
                    decoded,
                    b"",
                    status_code=messagebus_mod.ResponseStatusCode.UNSUPPORTED,
                )
            )
        else:
            responses.append(messagebus_mod.encode_read_response(decoded, payload))
    elif decoded.message_type is messagebus_mod.MessageType.SUBSCRIBE:
        if payload is None:
            responses.append(
                messagebus_mod.encode_subscribe_response(
                    decoded,
                    status_code=messagebus_mod.ResponseStatusCode.UNSUPPORTED,
                )
            )
        else:
            responses.append(messagebus_mod.encode_subscribe_response(decoded))
            responses.append(messagebus_mod.encode_notify(decoded.destination, payload))
    elif decoded.message_type is messagebus_mod.MessageType.UNSUBSCRIBE:
        if payload is None:
            responses.append(
                messagebus_mod.encode_unsubscribe_response(
                    decoded,
                    status_code=messagebus_mod.ResponseStatusCode.UNSUPPORTED,
                )
            )
        else:
            responses.append(messagebus_mod.encode_unsubscribe_response(decoded))
    elif decoded.message_type is messagebus_mod.MessageType.WRITE:
        if (
            decoded.destination in STARTUP_WRITE_ADDRESSES
            or decoded.destination in messagebus_mod.STARTUP_PROVIDER_PAYLOADS
        ):
            responses.append(messagebus_mod.encode_write_response(decoded))
        else:
            responses.append(
                messagebus_mod.encode_write_response(
                    decoded,
                    status_code=messagebus_mod.ResponseStatusCode.UNSUPPORTED,
                )
            )
    elif decoded.message_type is messagebus_mod.MessageType.RPC:
        if decoded.destination in STARTUP_RPC_ADDRESSES:
            responses.append(messagebus_mod.encode_rpc_response(decoded))
        else:
            responses.append(
                messagebus_mod.encode_rpc_response(
                    decoded,
                    status_code=messagebus_mod.ResponseStatusCode.UNSUPPORTED,
                )
            )

    return [
        mcsp.encode_frame(
            mcsp.Frame(
                end_of_channel=True,
                channel=frame.channel,
                payload=response,
            )
        )
        for response in responses
    ]


async def main(address: str, out_file: str | None = None) -> None:
    path = Path(out_file or f"ble_handshake-{ts()}.txt")
    print(f"Connecting to {address} ...", flush=True)
    print(f"Logging to {path}", flush=True)

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    async with live.connected_client(address, timeout=20.0) as client:
        print(f"Connected: {client.is_connected}", flush=True)
        receive_uuid, send_uuid = find_mcsp_transport(client.services)
        with path.open("a", encoding="utf-8") as fh:
            def emit(line: str) -> None:
                print(line, flush=True)
                fh.write(f"{line}\n")
                fh.flush()

            emit(f"{ts()} CONNECTED {address}")

            def log_notify(sender: object, payload: bytes) -> None:
                emit(f"{ts()} NOTIFY sender={sender} hex={payload.hex()} raw={payload!r}")
                emit(f"{ts()} NOTIFY-DECODED {live.summarize_packet(payload)}")

            session = live.McspLiveSession(
                client,
                receive_uuid,
                send_uuid,
                startup_responder=lambda frame, decoded: build_startup_response_packets(
                    frame=frame,
                    decoded=decoded,
                ),
                on_notify=log_notify,
                on_frame=lambda frame: emit(
                    f"{ts()} FRAME channel={frame.channel.name} end={frame.end_of_channel} hex={frame.payload.hex()}"
                ),
                on_command=lambda command: emit(f"{ts()} RECV command={command!r}"),
                on_message=lambda frame, decoded: emit(
                    f"{ts()} MESSAGE {messagebus_mod.format_message_frame(decoded)}"
                ),
                on_decode_error=lambda _item, exc: emit(f"{ts()} DECODE_FAILED error={exc}"),
                on_send=lambda packet: emit(f"{ts()} SEND hex={packet.hex()}"),
            )
            await session.start()
            try:
                commands = await session.wait_for_handshake(HANDSHAKE_TIMEOUT_SECONDS)
                await session.queue_handshake_response(commands)
                if not stop.is_set():
                    await asyncio.sleep(POST_HANDSHAKE_WAIT_SECONDS)
            finally:
                await session.stop()


def cli() -> None:
    if len(sys.argv) not in {2, 3}:
        print(f"Usage: {sys.argv[0]} <BLE_ADDRESS> [output_file]")
        raise SystemExit(2)

    address = validate_address(sys.argv[1])
    output = sys.argv[2] if len(sys.argv) == 3 else f"ble_handshake-{ts()}.txt"
    try:
        asyncio.run(main(address, output))
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"Error: {format_cli_error(exc)}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
