# Python lint and type-check cleanup

## Hypothesis

The failing Python checks come from inaccurate structural types and test fixtures,
rather than requiring changes to Bluetooth connection or protocol behavior.

## Setup

- Loaded `REMOTE_HOST` using `direnv`.
- Synced the current worktree to `~/bosch-ble`, removing stale remote source files
  while excluding Git metadata, virtual environments, captures, and Android files.
- Installed mise on the remote host because it was absent.
- Ran the repository's complete `mise check` task remotely.

## Observations

- Stale remote files initially referenced APIs absent from the current checkout.
  An exact source sync eliminated those unrelated diagnostics.
- Removing the existing `ty: ignore` comments exposed 26 type errors.
- The GATT protocol incorrectly required nested characteristics on a characteristic
  and invariant lists for read-only collections.
- Test fixtures inherited from concrete clients and assigned read-only properties;
  tuple, command lookup, and callback annotations also misrepresented their values.
- ESPHome's service collection is iterable but does not implement `len`, and may
  be absent before discovery.

## Result

Corrected the GATT protocol and defined the minimal client and socket interfaces
used by existing helpers. Repaired fixture annotations and service counting,
and removed every `ty: ignore` suppression without weakening check configuration.
Remote `mise check` passed Ruff, ty, and all 158 tests (43.83 seconds for pytest).

## Conclusion

The lint and type errors were resolved through accurate types and fixtures.
These checks establish automated regression coverage on Linux; no physical bike
connection or pairing validation was performed during this lint cleanup.
