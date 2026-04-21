# Hypothesis

The new `MGMT_OP_LOAD_CONN_PARAM` helper can be used from the normal user on `REMOTE_HOST`, because read-only `btmgmt` operations already work without `sudo`.

# Setup

- Host: Linux box reached via `REMOTE_HOST`
- Repo revision: local uncommitted `bosch_ble/mgmt.py` helper copied to the host worktree
- Probes used:
  - `uv run python -m bosch_ble.mgmt load-conn-params ...`
  - direct Python socket probes against the Bluetooth mgmt control channel
  - control mgmt reads:
    - `MGMT_OP_READ_VERSION`
    - `MGMT_OP_READ_COMMANDS`
  - control mgmt writes:
    - `MGMT_OP_SET_POWERED`
    - `MGMT_OP_SET_BONDABLE`
    - `MGMT_OP_LOAD_CONN_PARAM`

# Observations

- The raw Bluetooth mgmt socket opens and binds successfully as the normal user.
- Read-only mgmt commands send and receive successfully as the normal user:
  - `MGMT_OP_READ_VERSION`
  - `MGMT_OP_READ_COMMANDS`
- Trusted mgmt write commands fail at `sendall()` as the normal user with the same kernel error:
  - `MGMT_OP_SET_POWERED` -> `OSError: [Errno 12] Cannot allocate memory`
  - `MGMT_OP_SET_BONDABLE` -> `OSError: [Errno 12] Cannot allocate memory`
  - `MGMT_OP_LOAD_CONN_PARAM` -> `OSError: [Errno 12] Cannot allocate memory`
- The repo's first live run with the new helper failed before any BLE activity for a different reason:
  - `sudo` for `python -m bosch_ble.mgmt` required a password in the noninteractive SSH session
- The direct socket probes show that even without `sudo` prompting, `LOAD_CONN_PARAM` is still blocked unless the mgmt socket is trusted.

# Result

`MGMT_OP_LOAD_CONN_PARAM` is not available to the untrusted normal-user mgmt socket on this host. It needs the same trusted privilege level as other mgmt write commands.

# Conclusion

The new helper is not blocked by packet formatting. It is blocked by BlueZ/kernel trust requirements for mgmt write operations. The practical consequence is:

1. interactive repo runs may succeed if `sudo` can elevate `python -m bosch_ble.mgmt`
2. noninteractive SSH automation will fail unless the host has passwordless `sudo` for that helper or an equivalent trusted execution path
3. future work on `LOAD_CONN_PARAM` must treat trusted execution as a prerequisite, not as an optional convenience

# Next questions

1. Is passwordless `sudo` acceptable for `python -m bosch_ble.mgmt` on `REMOTE_HOST`, or should a narrower trusted wrapper be used instead?
2. If trusted execution is unavailable, is there any other BlueZ-supported path to per-device LE connection parameters without mgmt write privileges?
3. Once the helper can run with a trusted socket, does the actual `LE Create Connection` trace change from `20-40 ms / 4000 ms` to the intended phone-like values?
