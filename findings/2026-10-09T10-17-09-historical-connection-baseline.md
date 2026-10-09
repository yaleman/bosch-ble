# Hypothesis

The lost progress is associated with Linux connection setup rather than a demonstrated regression in the Android-derived MCSP/MessageBus implementation.

# Setup

- Historical investigation reviewed Git history through `995b28b`, the April findings, and the remote btmon logs named below.
- This note records that earlier examination; it is not a new live experiment or a claim that the old remote logs remain available today.
- Current implementation review includes subsequent ESPHome support through `c948d17`.
- The target was `00:04:63:BA:64:FC`, with an nRF52840 controller as `hci0` during the April 21 experiments.

# Observations

| Evidence | Initial LE Create Connection | Furthest observed traffic |
| --- | --- | --- |
| `final-privacy-off-1776758694.log` | 30/30 ms, latency 0, timeout 720 ms | ATT MTU exchange and GATT service discovery |
| `manual-pair-1776758573.log`, first attempt | 30/30 ms, latency 0, timeout 720 ms | Remote features, then disconnect `0x3e` |
| `dump-gatt-connect-first-1776759774.log` | 20/40 ms, latency 0, timeout 4000 ms | Remote features, then disconnect `0x3e` |
| `dump-gatt-run-1776768038.log` | 20/40 ms, latency 0, timeout 4000 ms | Remote features, then disconnect `0x3e` |
| `manual-control-run-1776768311.log` | 20/40 ms, latency 0, timeout 4000 ms | Remote features, then disconnect `0x3e` |

- The successful connection subsequently accepted a bike-requested update to 20/40 ms and 4000 ms. Those values are therefore not intrinsically incompatible with an established session.
- The same initial 30/30 ms values also appear in a failing attempt. Matching parameters alone does not prove success or establish causality.
- `2001cd3`, `bb7b929`, `ef0cca3`, and `5b725e2` added MCSP, validation, and MessageBus tooling on April 20. Test snapshots show the expected protocol shapes, but are not independent evidence of a successful live Python handshake.
- `f2bff94` added security staging before live MCSP work. `9f6ed4b` made a Bleak CCCD restriction trigger explicit pairing on an unpaired bike. These are later-stage behavior changes worth comparing if a fresh connection reaches GATT.
- `debe313` added controller preparation; `3fce717` switched the shared connection path to connect-first; `4a691e6` added a rescan after preparation.
- `1a88bb0` added per-device mgmt parameter loading, and later commits tightened privilege checks and advertisement gating. Successful mgmt loading does not itself prove the parameters used on air.
- The old manual helper loaded parameters without the repo's privacy/power setup or advertisement gate and suppressed connection failures.

# Result

There is confirmed historical evidence of Linux reaching ATT/GATT. The clearest baseline is the successful privacy-off manual run recorded in `findings/2026-04-21T20-30-00-privacy-off-connect.md`, incorporated into the connect-first design by `3fce717`.

No reviewed evidence identifies a single last-known-good Git revision for a stable, complete Python MCSP session. Describing April 20 as the proven best protocol revision would overstate the evidence.

# Conclusion

Use the historical successful trace as a comparison target: confirmed bike visibility, privacy off, initial 30/30 ms and 720 ms, followed by ATT/GATT. Investigate the actual on-air parameters and connection lifetime before attributing failure to MCSP responses.

The current experiment aligns the manual helper with shared controller preparation, gates both before and after controller reset, loads per-device parameters immediately before connect, and saves target-specific trace evidence. It performs no new pairing or MCSP interrogation.

This qualifies the earlier parameter findings: the parameter difference is a hypothesis to test, not an established root cause. A successful live comparison must include ATT and a connected, service-resolved state, not merely matching parameters or an HCI connection-complete event.
