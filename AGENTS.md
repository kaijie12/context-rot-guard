# Agent instructions (context-guard)

You are working in **context-guard**: a Python library and CLI that keeps the current unit of a chat in front of the model and redirects only when that unit is abandoned. Prefer small, reversible edits. Do not add an embedding provider, a UI, or a full agent runner unless the ask says so. Decisions live in `DECISIONS.md`.

## How to check (closed loop)

| Gate | Command |
| --- | --- |
| Unit | `python3 -m pytest -q` |

From a fresh checkout, install the test runner first: `python3 -m pip install -e ".[dev]"`.

Before claiming done: run that command and paste the command, the exit status, and the last lines of output. If it is red, fix and re-run until green. Do not weaken or delete tests under `tests/` to go green.

For a **guarded product session** (not this repo’s own pytest gate): run `context-guard quality-check` before declaring done. If it exits 2, do not claim done — fix drift or the verify command first. Users may run the same command anytime.

`examples/demo_drift_session.py` is a script, not a substitute for pytest. Run it when you change compaction, anchors, drift, or events:

```bash
python3 examples/demo_drift_session.py
```

## Never

- Read `.env`, `.env.*`, or files under `secrets/`
- `git push --force` / `git push -f`
- Deploy or migrate production
- Commit credentials or API keys
- `rm -rf /`
- Declare a guarded session done while `attempt_done()` would return `blocked`, or while `quality-check` exits 2 — do not bypass those checks in the library to make a demo look green

## Human gate — ask before

- Breaking changes to `ContextRotGuard.process()`, `attempt_done()`, or CLI flags (that is a major version)
- Adding a required network dependency (embeddings, hosted summarizers)
- Renaming the package `context-guard` or the `context-guard` console script

## Budget (per run)

- Stop after ~15 minutes wall clock or after the same failing command 3 times
- Prefer the cheapest model that works; one escalate if the cheap result is unusable
- If a hook or deny rule blocks you, explain the block — do not route around it

## Defaults

- The check command is pytest. Do not invent a second test runner.
- This package has no runtime dependencies. Keep it that way unless a human gate says otherwise.
- `EmbeddingDriftDetector` stays a stub until a task explicitly asks for Path A.
