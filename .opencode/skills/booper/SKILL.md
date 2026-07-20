---
name: booper
description: >-
  Use when interacting with the bike-button-booper ESPHome device over its
  remote API — toggling the solenoid relay, reading the physical button
  state, or controlling the onboard LED. Trigger on "booper", "button
  booper", "solenoid relay", or "ESP32_relay".
---

# Bike Button Booper (ESPHome remote API)

A standalone ESPHome device that physically presses the eBike button so the
bike stays awake without a human. Details live in
`docs/the-button-booper.md`.

## Connection facts

- **Hostname:** `bike-button-booper.local` (port `6053`, the ESPHome API).
- **Encryption key:** loaded from the `BOOPER_API_KEY` env var. It is the
  ESPHome `api.encryption.key` value: a base64 string. Pass it to
  `aioesphomeapi` as the `noise_psk` argument **verbatim** (no decoding
  needed).
- **Entities** (names match the YAML in `docs/the-button-booper.md`):
  - `switch` `ESP32_relay` — "Solenoid Relay" (the thing that taps the button).
  - `light` `onboard_led` — "Onboard Led" status LED.
  - `binary_sensor` `button` — "Button" (local physical press sensor).

## Library

`aioesphomeapi` is the supported client. It is **not** in this project's
`pyproject.toml`; install it in an isolated venv or `uv tool`/script context
rather than polluting the bosch-ble dependencies:

```bash
uv run --with aioesphomeapi python booper_script.py
```

## Minimal client

```python
import asyncio
import os

from aioesphomeapi import APIClient


async def main() -> None:
    client = APIClient(
        "bike-button-booper.local",
        6053,
        password="",
        noise_psk=os.environ["BOOPER_API_KEY"],
    )
    await client.connect(login=True)

    # Pulse the solenoid relay for ~200ms to tap the button.
    await client.switch_command("ESP32_relay", True)
    await asyncio.sleep(0.2)
    await client.switch_command("ESP32_relay", False)

    def on_state(state) -> None:
        # Prints when the local Button is pressed or the relay changes.
        print(state)

    client.subscribe_states(on_state)
    await asyncio.sleep(5)


asyncio.run(main())
```

## Notes

- The device only acts when it is powered and on the same LAN; resolve
  `bike-button-booper.local` (mDNS) before assuming it is reachable.
- Treat it as a physical actuator: do not spam `switch_command`. A short
  pulse (100–300 ms) is enough to register a button press.
- `subscribe_states` is the way to observe the local `Button` sensor; there
  is no polling endpoint that replaces it.
