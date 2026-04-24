# bosch-ble

Small Python CLI tools for investigating and interacting with a Bosch smart-system eBike over BLE through BlueZ and Bleak.

## Core Docs

- `docs/current-design.md`: canonical design document for the current implementation and live workflow
- `findings/README.md`: rules for recording live investigation results
- `docs/2026-04-20-pairing-blocker-summary.md`: focused note on the current pairing blocker
- `docs/makerdiary-ble-sniffer-ubuntu24.md`: over-the-air sniffer setup guide

## Common Commands

- `uv sync`
- `uv run bosch-ble-scan`
- `uv run bosch-ble-dump-gatt <BLE_ADDRESS>`
- `uv run bosch-ble-log-chars <BLE_ADDRESS> [output_file]`

## Verification

Bluetooth-related verification for this repo should run on the remote host referenced by `REMOTE_HOST` after syncing the worktree to `~/bosch-ble`.
