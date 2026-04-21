# Hypothesis

The Bosch bike only stays in the usable pairing advertisement state for a short window, and that timing is now a first-order factor in whether live runs produce valid evidence.

# Setup

- Host: Linux box addressed by `REMOTE_HOST`
- Controller: nRF52840 dongle as `hci0`
- Repo revision:
  - `4a691e6` for the connect-first plus post-controller-prep rescan path
- Two live checks were run:
  1. immediate repo run after confirming pairing advertisement
  2. follow-up manual connect script that waited for the same advertisement state

# Observations

- The immediate repo run did start while the bike was in the correct pairing advertisement state:
  - `ADV:PAIRING`
  - `LE Limited Discoverable Mode`
- That run still failed before ATT:
  - `Error: BlueZ connect failed for 00:04:63:BA:64:FC`
  - HCI trace only reached:
    - `LE Create Connection`
    - `LE Enhanced Connection Complete`
    - `LE Read Remote Used Features Complete`
- A follow-up control script then waited for the same pairing advertisement state before attempting a manual `bluetoothctl connect`.
- Across four scan windows in that control script, the bike never re-entered pairing advertisement:

```text
PAIRING_MODE:WAIT_1
PAIRING_MODE:WAIT_2
PAIRING_MODE:WAIT_3
PAIRING_MODE:WAIT_4
PAIRING_MODE:NO
```

# Result

The bike's pairing advertisement window is short enough that even back-to-back control attempts can miss it after a single live run.

# Conclusion

Future live comparisons need to assume the pairing advertisement state is ephemeral. A single successful gate does not imply a second attempt seconds later is still valid. That means:

1. one gated live run per user-confirmed pairing-screen window is the safe default
2. controls that need the same state must be launched immediately, not as a later follow-up
3. failed second attempts after the first gated run should be treated as bike-state misses first

# Next questions

1. On the next bike-on window, should the first gated attempt be the repo path or the manual control path?
2. Would a dedicated helper that gates on `LE Limited Discoverable Mode` and immediately runs one selected action reduce wasted live windows?
3. Is there a bike UI action that reliably re-arms pairing advertisement without leaving and re-entering the Bluetooth screen?
