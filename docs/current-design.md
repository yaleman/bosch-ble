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
- `docs/2026-04-20-pairing-blocker-summary.md`: focused note on the current pairing blocker and host-side explanation
- `docs/makerdiary-ble-sniffer-ubuntu24.md`: over-the-air capture setup for phone-versus-Linux comparisons
- `docs/superpowers/specs/2026-04-17-scanner-tui-design.md`: scanner-specific UI design note

## Verification

Bluetooth behavior in this repo is only considered validated when checks run on the remote host after syncing the worktree to `~/bosch-ble`.

Canonical verification commands:

```bash
ssh "$REMOTE_HOST" "cd ~/bosch-ble && uv run pytest -q"
ssh "$REMOTE_HOST" "cd ~/bosch-ble && uv run ruff check bosch_ble tests"
```

Local runs can help with fast feedback for pure unit coverage, but they are not sufficient evidence for live Bluetooth behavior.
