"""One visibility-gated BlueZ connection experiment, with retained evidence."""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import tempfile
from dataclasses import asdict
from enum import StrEnum
from pathlib import Path

from bosch_ble import bluez
from bosch_ble._common import format_cli_error, validate_address


class ConnectOutcome(StrEnum):
    BIKE_UNAVAILABLE = "bike_unavailable"
    SETUP_FAILED = "setup_failed"
    CONNECT_FAILED = "connect_failed"
    PARAMETERS_UNKNOWN = "parameters_unknown"
    PARAMETERS_DIFFER = "parameters_differ"
    NO_ATT = "no_att"
    BASELINE_REACHED = "baseline_reached"


def check_host() -> None:
    missing = [name for name in ("sudo", "btmon", "btmgmt", "bluetoothctl", "timeout", "script")
               if shutil.which(name) is None]
    if missing:
        raise RuntimeError(f"Missing host tools: {', '.join(missing)}")
    result = bluez.run_command(["sudo", "-n", sys.executable, "--version"])
    if result.returncode != 0:
        raise bluez.ConnectionSetupError(
            bluez.ConnectionSetupStep.SUDO, "controller", bluez.summarize_failure(result),
        )


async def check_capture() -> None:
    async with bluez.btmon_text_capture() as path:
        print(f"Passive capture ready: {path}", flush=True)
    print("Passive capture stopped. No scan or connection was attempted.")


async def capture_connection(address: str, directory: Path) -> ConnectOutcome:
    outcome = ConnectOutcome.CONNECT_FAILED
    error: str | None = None
    preflight: bluez.BluezState | None = None
    trace_path = directory / "btmon.log"
    try:
        bluez.assert_controller_ready(address)
        async with bluez.btmon_text_capture(path=trace_path):
            preflight = await bluez.preflight_device(address)
            bluez.print_preflight_summary(preflight)
            bluez.assert_pairing_advertisement_ready(preflight, address)
            await bluez.connect_device(address, verbose=True)
            await bluez.wait_for_state(address, connected=True, services_resolved=True)
            await asyncio.sleep(3.0)
            state = await asyncio.to_thread(bluez.read_device_state, address)
            if state.connected is True and state.services_resolved is True:
                outcome = ConnectOutcome.BASELINE_REACHED
    except bluez.BikeStateError as exc:
        outcome = ConnectOutcome.BIKE_UNAVAILABLE
        error = format_cli_error(exc)
    except bluez.ConnectionSetupError as exc:
        outcome = ConnectOutcome.SETUP_FAILED
        error = format_cli_error(exc)
    except Exception as exc:
        error = format_cli_error(exc)

    text = trace_path.read_text(errors="replace") if trace_path.exists() else ""
    summary = bluez.summarize_btmon_trace(
        text, pair_backend="connect", privacy="off",
        visible=preflight.visible if preflight else None,
        name=preflight.name if preflight else None, assist_error=error,
        trace_path=str(trace_path), address=address,
    )
    if outcome is ConnectOutcome.BASELINE_REACHED:
        if not summary.initial_parameters:
            outcome = ConnectOutcome.PARAMETERS_UNKNOWN
        elif any(p != bluez.PHONE_LIKE_PARAMETERS for p in summary.initial_parameters):
            outcome = ConnectOutcome.PARAMETERS_DIFFER
        elif not summary.att_seen:
            outcome = ConnectOutcome.NO_ATT
    bluez.print_pair_attempt_summary(summary)
    print(f"Outcome: {outcome.value}")
    (directory / "summary.json").write_text(
        json.dumps({"address": address, "outcome": outcome, **asdict(summary)}, indent=2) + "\n",
    )
    return outcome


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("address", type=validate_address, nargs="?", default="00:04:63:BA:64:FC")
    checks = parser.add_mutually_exclusive_group()
    checks.add_argument("--precheck", action="store_true", help="Check tools, sudo, and passive capture without scanning")
    checks.add_argument("--capture-check", action="store_true", help="Check passive monitor startup and cleanup only")
    args = parser.parse_args()
    try:
        if args.capture_check:
            asyncio.run(check_capture())
            return
        check_host()
        if args.precheck:
            asyncio.run(check_capture())
            print("Host tools, noninteractive sudo, and capture are ready. No bike test was run.")
            return
        directory = Path(tempfile.mkdtemp(prefix="bosch-connect-"))
        print(f"Evidence: {directory}", flush=True)
        outcome = asyncio.run(capture_connection(args.address, directory))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception as exc:
        print(f"Error: {format_cli_error(exc)}", file=sys.stderr)
        raise SystemExit(1) from exc
    if outcome is not ConnectOutcome.BASELINE_REACHED:
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
