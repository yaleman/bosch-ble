# Hypothesis

A prepared, visibility-gated connection-only experiment can compare the current
BlueZ setup against the historical ATT/GATT baseline without introducing MCSP
interrogation as another variable.

# Setup

- Synced the current worktree to the remote host through `REMOTE_HOST`, excluding
  local environment files, caches, Git metadata, and Android source trees.
- Used the locked Python environment on that host.
- Ran remote unit, lint, and type checks and passive monitor startup/cleanup checks.
- Did not scan for, pair with, or connect to the bike during preparation.

# Observations

- Remote final checks: `pytest -q` passed 169 tests; `ruff check` and `ty check`
  both passed. The first test run exposed an outdated string-based exception
  assertion, now replaced with a typed setup-step assertion.
- Existing type errors involved incorrect GATT structural types, concrete client
  annotations rejecting test doubles, optional service collections, and test
  fixture annotations. These were corrected rather than suppressed.
- Passwordless sudo permits the BlueZ executables, but not the Python management
  helper. Noninteractive host precheck stops with a typed sudo setup error.
- Piped btmon output initially buffered its startup banner until shutdown. A PTY
  around the permitted btmon command allowed the passive monitor to report ready
  before the five-second startup deadline. The successful smoke run exited
  cleanly; subsequent process inspection showed no btmon process left running.
- The interactive host script now authenticates sudo and checks prerequisites
  before asking the operator to turn on the bike. The actual connection attempt
  is performed once, and a failing outcome remains a failing shell exit status.

# Result

Code and remote checks are ready for the connection-only experiment. The live
session needs interactive sudo authentication followed by the bike-on prompt in
the same SSH session. No sudoers permissions were expanded.

# Conclusion

The preparation validates the harness and pure code, not bike connectivity or the
connection-parameter hypothesis. A new live finding must record the target's
confirmed advertisement, initial on-air parameters, ATT/GATT traffic, and final
connection state before claiming the historical baseline has been recovered.
