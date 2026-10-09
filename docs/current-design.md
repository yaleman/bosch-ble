# Current Design

This is the canonical design document for the current `bosch-ble` implementation.

Use this document when changing connection flow, pairing behavior, MCSP startup handling, or operator workflow. Keep it in sync with code changes that alter those behaviors.

## Scope

This repo is a Python CLI toolbox for investigating and interacting with a Bosch smart-system eBike over BLE from Linux via BlueZ.

The current scope is:

- discover the bike reliably
- establish a connect-first BlueZ path
- perform Bosch security staging when Bleak is connected
- handle enough MCSP and MessageBus startup traffic to inspect live behavior
- support debugging workflows with reproducible evidence in `findings/`

This repo is not yet a complete production client for the full Bosch protocol surface.

## Current Status

The transport and startup layers are implemented far enough to support live comparison against known-good phone behavior, but first-time pairing on Linux remains host- and controller-sensitive.

The most important practical constraints are:

- bike state is ephemeral and often invalidates runs
- generic visibility is not the same as Bosch pairing readiness
- trusted BlueZ management access is required for the connection-parameter helper
- meaningful validation must run on the remote host referenced by `REMOTE_HOST`

Treat `findings/` as the primary evidence base for live-state conclusions.

The historical Linux baseline reached ATT/GATT with privacy off and initial
LE connection intervals of 30/30 ms, latency 0, and a 720 ms supervision timeout.
Matching these settings is a comparison target, not proof of a working session.
The bike also requested 20/40 ms and 4000 ms after that successful connection;
initial setup and subsequent updates must be distinguished in trace analysis.
See `findings/2026-10-09T10-17-09-historical-connection-baseline.md` for the
evidence and its limits. No historical stable Python MCSP revision is established.

## Design Priorities

1. Fail early on bad evidence.
   If the bike is not visible or not in the expected pairing advertisement state, stop before attempting to diagnose protocol behavior.
2. Keep the connection path direct.
   Prefer small helpers around BlueZ, Bleak, MCSP, and MessageBus over large abstraction layers.
3. Preserve the freshest device state.
   After controller resets or rescans, use the newest BlueZ/Bleak device handle rather than stale cached objects.
4. Surface disconnects instead of hiding them in cleanup.
   Session shutdown should expose writer failures and should not deadlock while draining queued packets.
5. Keep historical evidence append-only.
   New live runs go into `findings/` rather than silently rewriting older conclusions.

## Architecture

### BlueZ and host orchestration

`bosch_ble/bluez.py` owns host-side BLE setup and BlueZ interaction:

- preflight scanning and advertisement checks
- controller preparation for the phone-like connection path
- pairing/trust/connect helpers
- the BlueZ pairing agent
- diagnostic summaries from `btmon`

The main connection and explicit pairing diagnostics share controller preparation,
post-reset scanning, readiness gating, and parameter loading. Parameter loading
happens immediately before the connect/pair operation and requires trusted mgmt
access. A failure stops the attempt rather than silently continuing.

Important invariants:

- `Visible: no` is a bike-state failure first, not protocol evidence
- unpaired connect attempts must reject generic visibility as sufficient readiness
- connection-parameter loading happens before the BlueZ connect attempt
- the connect-first path is the main user-facing path for live work

### Bleak connection and Bosch security staging

`bosch_ble/dump_gatt.py` owns the Bleak-side connection handoff:

- resolve a target device
- call `bosch_ble.bluez.connect_device()`
- preserve the freshest connected device handle/path
- open the Bleak connection
- stage Bosch security with the vendor descriptor when needed

Security staging behavior:

- if direct descriptor write works, continue
- if encryption/authentication is required, pair via the BlueZ agent and wait for the paired connected state
- if Bleak blocks direct CCCD writes and the device is already paired, do not force a second pairing path

### Live MCSP session handling

`bosch_ble/live.py` owns reusable live-session behavior:

- discover the MCSP transport characteristics
- accumulate fragmented command frames across notifications
- detect the bike handshake once the full command set has arrived
- serialize outgoing handshake and startup packets through a single writer task

Important invariants:

- handshake detection must accumulate command state across callbacks
- queued startup packets must be sent after the handshake response
- `stop()` must not deadlock if the writer task fails during disconnect conditions
- healthy shutdown should still allow already-queued packets to flush before exit

### Handshake and MessageBus startup

`bosch_ble/handshake.py`, `bosch_ble/mcsp.py`, and `bosch_ble/messagebus.py` own the Bosch protocol surface currently implemented in-repo:

- MCSP frame and command encode/decode
- enough handshake response generation to match the observed bike startup
- startup MessageBus responses for a focused set of known addresses

The current design goal is not full protocol completeness. The goal is to support live inspection and controlled startup behavior without overbuilding a generic framework.

### User-facing tools

Current entrypoints are small wrappers around the shared flow:

- `bosch-ble-scan`: compact terminal scanner
- `bosch-ble-dump-gatt`: connect and dump services/characteristics
- `bosch-ble-log-chars`: subscribe and poll readable characteristics
- `bosch-ble-probe`: write-focused probing helper
- `bosch-ble-handshake`: trace MCSP startup
- `bosch-ble-dashboard`: compact live dashboard

These commands should keep using the shared connection and session helpers instead of drifting into separate ad hoc connection logic.

## Canonical Live Flow

For the main connect-first path, the intended control flow is:

1. Confirm the controller is not already busy.
2. Scan for the target device.
3. Reject invisible-bike or wrong-advertisement states before connect.
4. Prepare the controller for the current phone-like connection attempt.
5. Load per-device LE connection parameters through the trusted mgmt helper.
6. Ask BlueZ to connect.
7. Use the freshest connected device/path when constructing the Bleak target.
8. Open the Bleak connection.
9. Perform Bosch security staging if the device requires pairing or encryption.
10. Start any higher-level MCSP or MessageBus work.

If any step after queueing MCSP startup traffic fails, cleanup should surface that failure rather than hanging.

## Evidence Model

The repo deliberately distinguishes three kinds of documentation:

- `docs/current-design.md`
  This file. It explains what the implementation is supposed to do.
- `findings/*.md`
  Timestamped lab notes from real investigations and live runs.
- task-specific docs under `docs/`
  Deeper notes such as the pairing blocker summary or sniffer setup guide.

When deciding whether to change behavior:

1. read the relevant code path
2. read the relevant `findings/` notes
3. update this design doc if the intended behavior changed
4. add a new finding if new live evidence changed the conclusion

## Related Docs

- `findings/README.md`: rules for recording live evidence
- `findings/2026-10-09T10-17-09-historical-connection-baseline.md`: historical connection comparison
- `docs/2026-04-20-pairing-blocker-summary.md`: focused note on the current pairing blocker and host-side explanation
- `docs/makerdiary-ble-sniffer-ubuntu24.md`: over-the-air capture setup for phone-versus-Linux comparisons
- `docs/superpowers/specs/2026-04-17-scanner-tui-design.md`: scanner-specific UI design note

## Verification

Bluetooth behavior in this repo is only considered validated when checks run on the remote host after syncing the worktree to `~/bosch-ble`.

Canonical verification commands:

```bash
ssh "$REMOTE_HOST" "cd ~/bosch-ble && uv run pytest -q"
ssh "$REMOTE_HOST" "cd ~/bosch-ble && uv run ruff check"
ssh "$REMOTE_HOST" "cd ~/bosch-ble && uv run ty check"
```

Run all test, lint, and type verification remotely after syncing the worktree.
Passing those checks does not establish live Bluetooth behavior.

## Prepared Connection Experiment

Prepare and sync the full code and test script before requesting a bike-on window.
Load `REMOTE_HOST` through direnv. Run remote pytest, Ruff, and ty before live work.
The existing `scripts/manual-connect-after-load-conn` wrapper launches the host
script, which authenticates sudo and checks prerequisites while the bike can stay
off. It then prompts for the bike-on window, runs `bosch_ble.trace_connect` once,
and retains terminal output. The cached sudo credential stays in the same
interactive session; an unrelated SSH session cannot be assumed to share it.

The experiment checks controller availability, confirms advertisement visibility,
uses the shared connect-first setup with privacy off, waits for service resolution,
and checks the connection again after three seconds. It stops on failed readiness,
setup, or connection without retrying. It does not remove bonds or send MCSP traffic.
An unpaired bike must advertise Bosch pairing readiness; paired bikes may use their
ordinary advertisement state.

`uv run python -m bosch_ble.trace_connect --precheck` checks required host tools,
noninteractive sudo, and actual passive monitor startup/cleanup without scanning
or connecting. Use it in the same interactive session before the bike-on window.
`--capture-check` runs just the passive monitor check without requiring privileges
for the Python management helper.
The live run captures btmon before any BLE activity and saves `btmon.log` and
`summary.json` in the printed temporary evidence directory. Capture startup must
succeed before scanning; the capture process is bounded and unrelated captures
are not killed. A PTY keeps btmon output line-buffered without granting sudo
access to a general-purpose wrapper command. The monitor wrapper uses null stdin
so the timeout process group's terminal reads cannot suspend startup. Setup
failures before preflight report `Visible: unknown`, not a scan miss.

The summary uses enum outcomes and stages. It scopes events to the target address
and connection handles, excludes capability listings, and records every complete
initial LE Create Connection parameter set separately from later updates.
`baseline_reached` requires matching initial parameters, observed ATT traffic,
and a connected, service-resolved state after the observation interval. Other
outcomes identify unavailable bike state, setup failure, connection failure,
unknown/different parameters, or missing ATT evidence. This experiment establishes
a transport baseline only; pairing and a sustained MCSP session need later evidence.
