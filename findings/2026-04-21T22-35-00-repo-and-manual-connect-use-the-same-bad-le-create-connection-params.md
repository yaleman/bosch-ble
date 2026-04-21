# Hypothesis

The remaining pre-ATT disconnect is not caused by repo sequencing. Both the repo path and a plain manual BlueZ connect path are still using the same wrong initial LE connection parameters.

# Setup

- Host: Linux box reached via `REMOTE_HOST`
- Controller: nRF52840 dongle as `hci0`
- Bike state: confirmed pairing advertisement window
- Repo path evidence:
  - output: `/tmp/dump-gatt-run-1776768038.out`
  - trace: `/tmp/dump-gatt-run-1776768038.log`
- Manual control evidence:
  - output: `/tmp/manual-control-run-1776768311.out`
  - trace: `/tmp/manual-control-run-1776768311.log`

# Observations

- The repo connect-first path and the manual `bluetoothctl connect` path both reached the same HCI milestones:
  - `LE Create Connection`
  - `LE Enhanced Connection Complete`
  - `LE Read Remote Used Features Complete`
- Neither path reached ATT or SMP before the link died.
- Both traces used the same initial LE connection parameters:
  - minimum connection interval `20.00 ms (0x0010)`
  - maximum connection interval `40.00 ms (0x0020)`
  - supervision timeout `4000 ms (0x0190)`
- Both traces then failed before ATT with the same low-level shape.
- This happened even though the host had already been configured for phone-like defaults in `main.conf`.

# Result

The repo path and the plain manual control path are equivalent at the critical pre-ATT layer, and both are still using the same non-phone-like `LE Create Connection` parameters.

# Conclusion

At this point the repo was not adding a unique bug in the connection sequence. The host stack itself was still choosing `20-40 ms / 4000 ms` for the actual on-air connection attempt, so any fix needed to target BlueZ or the controller management layer rather than Bosch protocol code.

# Next questions

1. Can the host force per-device LE connection parameters more directly than `main.conf` or `set-sysconfig`?
2. Does BlueZ expose a per-device connection-parameter path that is not used by plain `bluetoothctl connect`?
3. If a lower-level mgmt command exists for per-device connection parameters, can the repo drive it before connect or pair?
