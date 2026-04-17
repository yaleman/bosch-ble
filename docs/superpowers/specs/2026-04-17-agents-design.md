# `AGENTS.md` Design

## Goal

Create a minimal, agent-focused `AGENTS.md` at the repository root that helps coding agents work effectively in this repo without repeating generic platform guidance.

## Constraints

- Keep the file short enough to scan in one screen.
- Include only repository-specific guidance.
- Prefer direct Python changes over abstractions or extensibility work.
- Use project-relative paths in documentation and comments.
- Preserve existing local changes, including the unstaged edit in `bosch_ble/scan.py`.

## Proposed Structure

### Project Shape

State that this repo is a small Python CLI package with source under `bosch_ble/` and command entry points defined in `pyproject.toml`.

### Preferred Commands

List the commands agents should actually use:

- `uv sync`
- `uv run bosch-ble-scan`
- `uv run bosch-ble-dump-gatt <BLE_ADDRESS>`
- `uv run bosch-ble-log-chars <BLE_ADDRESS> [output_file]`
- `uv run pytest`
- `uv run ruff check`

### Editing Rules

Keep the guidance narrow:

- Make focused changes in the existing scripts instead of adding layers.
- Reduce code sprawl while editing.
- Use package managers for dependency changes.
- If JavaScript tooling appears later, prefer `pnpm`.

### Output Guidance

Call out the current scanner expectation explicitly:

- Terminal output should favor compact table-style presentation over verbose scrolling logs.

### Documentation Rules

Include the path rule because it is easy for agents to violate:

- In docs and comments, use project-relative paths and avoid absolute on-disk paths.

## Out of Scope

- Human contributor onboarding
- Commit conventions
- Broad style rules already covered by higher-level agent instructions
- Architecture guidance beyond the current small CLI layout

## Review Check

This design is intentionally minimal. The resulting `AGENTS.md` should be roughly 15 to 30 lines and should not introduce process overhead.
