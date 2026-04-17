# Scanner TUI Design

## Goal

Replace the current verbose scanner output with an interactive terminal UI that is compact, keyboard-driven, and usable over SSH.

## Constraints

- Keep scanning behavior in `bosch_ble/scan.py`.
- Preserve the existing local change that suppresses blank names.
- Add `textual` through the package manager instead of editing dependency metadata by hand.
- The UI must work in a normal interactive terminal over SSH.
- Do not rely on mouse input, local GUI integration, or terminal features that are commonly unavailable in remote sessions.

## Proposed Behavior

### Layout

Use a two-pane layout:

- Left pane: device table
- Right pane: details for the selected device
- Bottom line: short key hints and current mode state

### Device Table

Show one row per seen device with these columns:

- `Name`
- `Address`
- `RSSI`
- `Seen`
- `Age`

Rows update live as advertisements arrive.

### Detail Pane

Show the selected device's:

- service UUIDs
- manufacturer data
- service data

Format byte payloads compactly and truncate long values consistently.

### Interaction

Keyboard-only controls:

- arrow keys to change selection
- `s` to cycle sort modes
- `f` to toggle hiding stale devices
- `q` to quit

Initial sort should favor the most relevant live view rather than alphabetical browsing.

### SSH Compatibility

Design for standard TTY use:

- no mouse requirement
- readable in narrow terminals
- stable redraw behavior over remote latency
- no dependence on clipboard, hyperlinks, or other local-terminal extras

## Implementation Shape

- Keep BLE discovery state in a simple shared in-memory structure.
- Split pure presentation helpers from BLE event handling so table rows and detail strings can be tested without running the full TUI.
- Let the `textual` app poll or refresh from current device state on a short interval rather than printing directly from the scanner callback.
- Shut down scanning cleanly when the app exits.

## Testing Focus

- Pure formatting helpers for age, byte display, and row/detail rendering
- Sort mode behavior
- Stale-device filtering
- Empty-state behavior before any devices are seen
- Safe rendering when optional fields such as name, UUIDs, or advertisement payloads are missing

## Review Check

This design intentionally targets an SSH-safe interactive terminal UI, not a rich local-only dashboard. The implementation should stay direct and avoid building a generic TUI framework around the scanner.
