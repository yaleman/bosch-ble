# Hypothesis

The capture wrapper's inherited terminal input prevents monitor startup under
interactive SSH, although the same wrapper starts under noninteractive SSH.
This is a harness failure, not evidence of a bike advertising or protocol failure.

# Setup

- Inspected the operator's `bosch-connect-6bixpzfk` evidence directory on the
  remote host. The run used the prepared interactive SSH helper and tee pipeline.
- Added a complete `--capture-check` command before running reproductions. It
  opens and closes a passive monitor without scanning, pairing, or connecting.
- Reproduced with `ssh -tt`, then tested the stdin-isolation fix with interactive
  SSH both directly and through tee.
- Synced the worktree and ran all code checks on the remote host.

# Observations

- The operator's btmon log was empty. The summary reported `setup_failed` before
  preflight; its `visible: false` was a default, not an advertisement observation.
- The original capture wrapper reproduced the startup timeout under `ssh -tt`,
  retaining another empty capture log. Earlier preparation had only demonstrated
  startup under noninteractive SSH.
- GNU timeout creates a separate process group by default. Allowing its script
  child to inherit the interactive terminal input introduces terminal job-control
  reads into a passive monitor pipeline.
- Setting capture stdin to null, while retaining the PTY for btmon's line-buffered
  output, allowed startup and shutdown under both tested interactive transports.
- The tee-pipeline check retained the monitor version banner and controller
  initialization events. Subsequent process inspection showed no remaining
  monitor, script, or timeout processes.
- Remote checks passed: 172 unit tests, Ruff, and ty.

# Result

The terminal-dependent capture startup failure is fixed in the reproduced setup.
The host precheck now tests actual monitor startup and cleanup before prompting
for the bike. Failures before advertisement scanning report unknown visibility.

# Conclusion

This finding qualifies the readiness conclusion in
`findings/2026-10-09T10-29-26-connection-harness-preparation.md`: noninteractive
capture validation was insufficient for an interactive SSH workflow.

The operator's failed run gives no evidence for or against bike visibility,
connection parameters, pairing, or MCSP behavior. A fresh bike-on connection
experiment is still required. No live connection attempt was made during this fix.
