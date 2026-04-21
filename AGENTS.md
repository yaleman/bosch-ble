# Agent Guide

## Project Shape
- Small Python CLI package.
- Source lives under `bosch_ble/`.
- CLI entry points are defined in `pyproject.toml`.

## Preferred Commands
- `uv sync`
- `uv run bosch-ble-scan`
- `uv run bosch-ble-dump-gatt <BLE_ADDRESS>`
- `uv run bosch-ble-log-chars <BLE_ADDRESS> [output_file]`
- `uv run pytest`
- `uv run ruff check`

## Editing Rules
- Keep changes direct and prefer editing the existing scripts.
- Reduce code sprawl while working; do not add layers without a clear need.
- Use package managers for dependency changes.
- If JavaScript tooling appears, prefer `pnpm`.
- The remote dev box worktree may be overwritten freely when needed; do not preserve or tiptoe around remote-only changes there.
- Load `REMOTE_HOST` from the local shell environment via `direnv` before using host-helper scripts or SSH-based workflows.
- The bike often turns off or stops advertising between attempts.
- Before diagnosing protocol or pairing failures, confirm the bike is awake and visible to BlueZ.
- Treat `Visible: no`, scan misses, and `Device ... not available` as bike-state failures first.
- Only use runs with confirmed advertisement visibility as evidence for pairing or protocol conclusions.
- When you finish a request, commit and push the changes.

## Output Guidance
- Scanner output should favor compact table/TUI-style terminal views over verbose scrolling logs.

## Docs And Comments
- Use project-relative paths only.
- Do not use absolute on-disk paths in docs or comments.
