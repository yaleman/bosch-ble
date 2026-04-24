# Agent Guide

## Project Shape
- Small Python CLI package.
- Source lives under `bosch_ble/`.
- CLI entry points are defined in `pyproject.toml`.

## Preferred Commands
- Local command examples only:
  - `uv sync`
  - `uv run bosch-ble-scan`
  - `uv run bosch-ble-dump-gatt <BLE_ADDRESS>`
  - `uv run bosch-ble-log-chars <BLE_ADDRESS> [output_file]`
  - `uv run pytest`
  - `uv run ruff check`
- Verification rule:
  - Do not treat local `pytest`, `ruff`, or other Bluetooth-related runs as valid evidence.
  - Run test and lint verification on the remote host via `REMOTE_HOST`.
  - If code changes need verification, sync the current worktree to `~/bosch-ble` on the remote host first, then run the checks there.

## Editing Rules
- Keep changes direct and prefer editing the existing scripts.
- Reduce code sprawl while working; do not add layers without a clear need.
- Use package managers for dependency changes.
- If JavaScript tooling appears, prefer `pnpm`.
- The remote dev box worktree may be overwritten freely when needed; do not preserve or tiptoe around remote-only changes there.
- Load `REMOTE_HOST` from the local shell environment via `direnv` before using host-helper scripts or SSH-based workflows.
- Bluetooth code cannot be validated locally in this repo. All meaningful test and lint runs need to happen on the remote host.
- The bike often turns off or stops advertising between attempts.
- Before diagnosing protocol or pairing failures, confirm the bike is awake and visible to BlueZ.
- Treat `Visible: no`, scan misses, and `Device ... not available` as bike-state failures first.
- Only use runs with confirmed advertisement visibility as evidence for pairing or protocol conclusions.
- Record meaningful investigation results in timestamped markdown files under `findings/`.
- Write findings like a scientific lab notebook entry: state the hypothesis, setup, observations, result, and conclusion.
- Prefer filenames like `findings/2026-04-21T18-05-00-privacy-off-connect.md` so later work can sort and reference them easily.
- When proposing a plan or evaluating an idea, review the relevant `findings/` notes first and use them as evidence for or against the next step.
- If a new live run invalidates an older conclusion, add a new finding that supersedes it instead of silently overwriting history.
- When you finish a request, commit and push the changes.

## Output Guidance
- Scanner output should favor compact table/TUI-style terminal views over verbose scrolling logs.

## Docs And Comments
- The canonical implementation guide is `docs/current-design.md`. Review it before substantial behavior changes and keep it in sync when the intended design changes.
- Use project-relative paths only.
- Do not use absolute on-disk paths in docs or comments.
