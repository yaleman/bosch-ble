# Pairing Blocker Summary

## Summary
Bosch transport work has moved forward substantially, but first-time pairing on `m710qa.local` is still blocked. The main complication is that the bike frequently turns off or stops advertising between attempts, so many failures are invalid as protocol evidence. At least one traced run was still a real pairing failure with the bike awake, visible, and briefly connected, so this is not only a power-state problem. The current best explanation is a host-side SMP pairing mismatch on the Linux adapter/controller, with higher-level Bosch protocol work blocked behind that.

## What Works
- Discovery works when the bike is awake and advertising as `smart system eBike`.
- The Python path now gets through preflight, BlueZ-assisted connection setup, and Bosch MCSP startup work more reliably than earlier revisions.
- MCSP and MessageBus startup handling are implemented far enough to compare live Linux behavior against the phone capture.
- `tmux` plus `btmon` is now a reliable way to capture a full pairing attempt without losing the TTY-backed session.
- The Python pairing path now sends `KeyboardDisplay` with `Bonding, MITM, SC, CT2`, which is much closer to the phone than plain `bluetoothctl pair`.

## What Fails Right Now
- First-time bond on `m710qa.local` still fails with `org.bluez.Error.AuthenticationCanceled`.
- Some runs fail earlier because the bike is simply not advertising, which makes them inconclusive for protocol debugging.
- The bike can connect briefly and still reject the pairing request before any secure session is established.
- Dashboard and higher-level Bosch protocol validation remain blocked until pairing is stable.

## Evidence
This section separates confirmed evidence from likely cause and from runs that are inconclusive due to bike state.

### Invalid / Inconclusive Runs
- `Visible: no` during preflight.
- Scan windows where `smart system eBike` or `00:04:63:BA:64:FC` never appeared.
- `Device 00:04:63:BA:64:FC not available`.
- Any run where the bike was not confirmed on-air immediately before the pair attempt.

These runs are best treated as bike-state failures first. They do not prove anything about Bosch pairing behavior.

### Valid Pairing-Failure Runs
- The bike was visible and advertising.
- The host connected briefly.
- The host sent an SMP Pairing Request.
- The bike disconnected with `Remote User Terminated Connection (0x13)`.

This is confirmed evidence of a real pairing mismatch even when the bike is awake.

## Phone vs Linux Pairing Request

| Source | IO capability | AuthReq | Initiator keys | Responder keys |
| --- | --- | --- | --- | --- |
| Known-good phone capture | `KeyboardDisplay` | `Bonding, MITM, SC, CT2` | `0x0b` = `LTK + IRK + LinkKey` | `0x0b` = `LTK + IRK + LinkKey` |
| Current Linux Python path | `KeyboardDisplay` | `Bonding, MITM, SC, CT2` | `0x0d` = `LTK + CSRK + LinkKey` | `0x0f` = `LTK + IRK + CSRK + LinkKey` |
| Plain `bluetoothctl pair` | weaker request | `No bonding, No MITM, SC, CT2` | worse than Python path | worse than Python path |

Confirmed evidence:
- The Linux Python path now matches the phone on IO capability and `AuthReq`.
- The remaining known mismatch is key distribution.

Likely cause:
- BlueZ on this host is still advertising `CSRK` and omitting initiator `IRK`, while the phone uses `IRK` and no `CSRK`.

## Host Findings
- Controller `bondable` state matters and was not consistently preserved across attempts.
- Forcing `pairable on` before pairing is necessary, but it did not by itself resolve the mismatch.
- Controller `privacy` support exists, but enabling it on this adapter was rejected.
- The current CSR-based adapter/controller remains a strong suspect because the phone-like SMP request is still not reproduced.

Confirmed evidence:
- `btmgmt info` shows `privacy` is supported.
- `btmgmt privacy on` is rejected on this host.
- The Python path can still send the wrong key distribution even after bondable-related improvements.

Likely cause:
- Adapter/controller behavior is preventing Linux from advertising the same bonding and identity capabilities as the phone.

## What Needs Doing
1. Make every future pairing test visibility-confirmed.
   Do not interpret failures unless the bike was confirmed awake and advertising in the same attempt window.
2. Fix the host/controller pairing behavior.
   Focus on the Linux SMP request until it matches the phone capture more closely, especially the `IRK` versus `CSRK` distribution.
3. Resume higher-level Bosch protocol work only after secure pairing is stable.
   MCSP and MessageBus work should continue after Linux can maintain a secure session with the bike.

## Useful Commands
Confirm visibility first:

```bash
bluetoothctl --timeout 12 scan on | tee /tmp/bike-scan.out
grep -E '00:04:63:BA:64:FC|smart system eBike' /tmp/bike-scan.out
```

Run a traced Python-path handshake:

```bash
tmux new-session -d -s boschpy -n btmon "sudo btmon -w /tmp/boschpy.snoop"
tmux new-window -t boschpy -n shell
tmux send-keys -t boschpy:shell.0 "cd ~/bosch-ble && bluetoothctl remove 00:04:63:BA:64:FC >/dev/null 2>&1 || true && BOSCH_BLE_AGENT_LOG=/tmp/bosch-agent.log uv run bosch-ble-handshake 00:04:63:BA:64:FC /tmp/bosch-live-handshake.log" C-m
```

Decode the captured pairing request:

```bash
sudo btmon -r /tmp/boschpy.snoop > /tmp/boschpy.decode.txt
sed -n '/SMP: Pairing Request/,+20p' /tmp/boschpy.decode.txt
```

Known-good comparison target from the phone capture:
- IO capability: `KeyboardDisplay`
- AuthReq: `Bonding, MITM, SC, CT2`
- Initiator key distribution: `0x0b`
- Responder key distribution: `0x0b`
