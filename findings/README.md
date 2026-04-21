# Findings

Use `findings/` as the repo's timestamped investigation log.

Each file should capture one meaningful experimental result and should be append-only at the repo level: add a new note when the evidence changes instead of rewriting old conclusions.

## Filename format

Use filenames like:

- `findings/2026-04-21T18-05-00-privacy-off-connect.md`
- `findings/2026-04-21T18-22-00-pairing-screen-advertising.md`

Keep the timestamp first so the directory sorts chronologically.

## Note structure

Write each note like a scientific lab record:

1. `Hypothesis`
2. `Setup`
3. `Observations`
4. `Result`
5. `Conclusion`
6. `Next questions`

Include exact commands, trace names, and concrete failure strings where they matter.

## How to use findings

- Before proposing a new plan, scan the relevant `findings/` notes for prior evidence.
- When a later run contradicts an earlier idea, add a new note that explicitly says what changed.
- Treat `findings/` as the evidence base for future debugging, not as a polished narrative.
