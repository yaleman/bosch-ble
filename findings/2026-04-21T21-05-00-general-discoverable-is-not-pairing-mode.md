# Hypothesis

Recent live failures after the connect-first change are invalid because the bike is advertising in its generic discoverable state rather than the specific pairing-mode advertisement that matched the known-good phone capture.

# Setup

- Host: the Linux box reached via `REMOTE_HOST`
- Controller: nRF52840 dongle as `hci0`
- Repo revision on host: `3fce717`
- Evidence sources:
  - fresh advertisement capture: `/tmp/adv-check-1776760003.log`
  - failed connect-first run:
    - output: `/tmp/dump-gatt-connect-first-1776759774.out`
    - trace: `/tmp/dump-gatt-connect-first-1776759774.log`
  - known-good phone capture reference:
    - `captures/bosch-2026-04-19-2108-with-pairing.pcapng`

# Observations

- The bike was visible in the scan gate:

```text
[NEW] Device 00:04:63:BA:64:FC smart system eBike
```

- The live connect-first run still failed early:

```text
Error: BlueZ connect failed for 00:04:63:BA:64:FC: [CHG] Device 00:04:63:BA:64:FC Connected: no
Visible: yes
Name: smart system eBike
```

- The corresponding HCI trace for that attempt only reached:
  - `LE Create Connection`
  - `LE Enhanced Connection Complete`
  - `LE Read Remote Used Features Complete`
  - then dropped before ATT
- The fresh advertisement capture shows the bike currently advertising as:
  - `Connectable undirected - ADV_IND`
  - `Flags: 0x06`
  - `LE General Discoverable Mode`
  - `BR/EDR Not Supported`
  - complete name `smart system eBike`
- It did **not** include the Bosch pairing-mode scan response seen in the known-good state.
- The earlier known-good pairing-state evidence was different:
  - `LE Limited Discoverable Mode`
  - Bosch manufacturer scan response payload `10eb01030001`

# Result

The bike being merely visible as `smart system eBike` is not enough to treat a run as equivalent to the known-good pairing state.

# Conclusion

Current live failures cannot be interpreted as regressions in the connect-first repo path unless the bike is first confirmed to be advertising in the pairing-mode pattern that matches the phone capture. Right now the bike is on-air, but only in its generic `LE General Discoverable Mode` advertisement, so the latest connect failure is still confounded by bike state.

# Next questions

1. What exact UI state on the bike produces the `LE Limited Discoverable Mode` plus Bosch scan response advertisement?
2. Should the repo gain a stronger preflight check for pairing diagnostics so it distinguishes generic visibility from the real pairing advertisement?
3. Once the bike is confirmed in that stricter pairing advertisement state, does the connect-first path reach ATT again on the current repo revision?
