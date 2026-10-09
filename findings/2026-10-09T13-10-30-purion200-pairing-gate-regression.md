# Hypothesis

The readiness gate rejects a valid Purion 200 pairing advertisement because it
compares the complete manufacturer payload with a four-byte suffix.

# Setup

- Inspected the operator's saved `bosch-connect-92rx4n32` run on the remote host.
- The operator used a Purion 200 and the interactive connection-only harness.
- Compared target advertisement events against historical successful pairing
  evidence and the locally available Android BES3 advertisement mapper.
- Reviewed the introduction of the readiness check in commit `720366d`.
- Synced the corrected worktree to the remote host for code verification.
- Did not start another scan or connection attempt during this investigation.

# Observations

- The saved run confirmed visibility and stopped before LE Create Connection.
  It reported `PairingAdvertisement: no` and `Outcome: bike_unavailable`.
- Starting near capture offset 0.646 seconds, the target emitted a scan response:

```text
Event type: Scan response - SCAN_RSP (0x04)
Address: 00:04:63:BA:64:FC (Bosch Security Systems)
Company: Robert Bosch GmbH (678)
  Data: 10eb01030001
```

- Associated advertisements reported flags `0x05`, LE Limited Discoverable Mode,
  service `0xfe02`, and the name `smart system eBike`. The pairing payload appeared
  repeatedly during the scan, including near its end.
- That matches the pairing state recorded in
  `findings/2026-04-21T20-30-00-privacy-off-connect.md`; this was not merely a
  generic discoverable advertisement.
- `720366d` introduced exact comparison against `01030001`. Bleak removes the
  company identifier but keeps all six payload bytes, so that comparison rejected
  the actual `10eb01030001` payload.
- The Android method `bes3AdvertisementInformation` in
  `android-app/decompiled-base/smali_classes3/com/bosch/ebike/bluetoothcommunication/internal/bes3/BES3AdvertismentDataMappingKt.smali`
  selects company `0x02A6`, requires six bytes, reads component version at offset 2,
  component ID at 3, data format at 4, and pairability at 5. A pairability value of
  1 means pairable. The prefix bytes are not interpreted by that mapper.
- The repo's Android pairing guide previously omitted the prefix and stated the
  wrong pairability offset. It has been corrected against the actual source.
- Scanner shutdown could also overwrite a pairing-ready scan response with a
  later ordinary advertisement. The scan now retains its first confirmed pairing
  response; each later scan must independently establish readiness again.

# Result

The pairing-readiness implementation now selects the Bosch manufacturer entry,
validates its length, and reads the pairability field instead of comparing an
exact component-specific byte string. Regression coverage includes the captured
payload, nonpairable flags, wrong companies, malformed lengths, other component
IDs, and a callback arriving during scanner shutdown.

Remote verification passed: 188 unit tests, Ruff, and ty. No fresh live connection
was attempted during verification.

# Conclusion

The operator correctly entered the expected pairing state. The reported readiness
failure was a code regression introduced by `720366d`, not a bike-state failure.
This is a concrete pre-connection blocker in the project history, but does not
establish why earlier attempts that actually connected later disconnected.

This finding supersedes any interpretation of this operator run as proof that
the bike was not pairing-ready. It also corrects the byte-offset assertion in
`findings/2026-07-23T12-00-00-bleak-esphome-implementation-plan.md` without rewriting
that historical note. A fresh connection attempt is still required to establish
whether the initial-parameter and ATT/GATT baseline is recovered.
