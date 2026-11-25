---
name: follow-the-loop
description: >-
  Repeatable loop for any new feature: write a machine-checkable acceptance
  file before coding, correct one unit, and stop on attempt cap or no
  progress. Use when adding a feature, scaffolding work, or when the user
  asks to follow the loop, loop principles, or a feature pack.
---

# Follow the loop

Use this for every new feature. The same steps apply in this repo and in any repo you copy this skill into. Do not invent a one-off process.

The loop makes one unit correct. A graph of workers is out of scope until one unit goes green without you.

## Before any product edit

1. Name one unit (a slug: lowercase words, hyphens).
2. Write the acceptance pack **before** implementation code:

```bash
python3 -m context_rot_guard feature start \
  --slug <slug> \
  --goal "<one sentence>" \
  --done-means "<what a program can decide>" \
  --check-cmd "python3 -m pytest -q" \
  --allow-path <path-you-may-edit> \
  --constraint "<what you will not touch>"
```

That writes `.context-rot-guard/features/<slug>/acceptance.json` and `BRIEF.md`. If the command is unavailable, copy [templates/acceptance.json](templates/acceptance.json) and fill it in. Do not start coding without that file.

3. The check command is the oracle. These are **not** checks, and they never authorize done:
   - the model says done
   - the diff looks reasonable
   - no exception was raised

## While building

1. Produce a change only inside `allow_paths`.
2. Run the check command.
3. If you opened a guard session (`context-rot-guard init` using the `BRIEF.md` session line), record the exit with `context-rot-guard check --exit-code N`.
4. On red, read the correction (`messages` includes `meta.kind=correction`). Fix **that unit only**. Do not regenerate unrelated work.
5. Paste the command and the last lines of output before claiming done.

## Exits (stop; do not polish)

| Exit | What you do |
| --- | --- |
| Pass | Check exits 0. Then you may say done. |
| Attempt cap | Default 3 trailing red checks. Stop and escalate. |
| No progress | Default 2 identical red outputs. Stop and replan. |
| Error threshold | `verify_stall` on the session. Same as the fail streak. |
| Human interrupt | User revises the goal or tells you to stop. |
| External event | The outcome already landed somewhere else. Archive the pack. |
| Cost budget | Harness budget in `AGENTS.md` / `sandbox.example.toml` (~15 minutes, 3 identical failures). |
| Deadline | Same harness wall clock. The prompt does not extend it. |

`next_route=escalate` means stop correcting. `next_route=correct` means one more scoped fix.

## Acceptance schema

```json
{
  "slug": "export-api",
  "goal": "Add a CSV export",
  "done_means": "python3 -m pytest -q exits 0",
  "constraints": ["do not edit tests to force green"],
  "allow_paths": ["src/context_rot_guard/export.py"],
  "acceptance": {
    "check_cmd": "python3 -m pytest -q",
    "expected_exit": 0,
    "green_rules": ["python3 -m pytest -q exits 0"],
    "not_a_check": ["The model says done", "The diff looks reasonable", "No exception was raised"],
    "unit_id": "export-api"
  },
  "exits": {
    "pass": "acceptance.check_cmd exits 0",
    "attempt_cap": 3,
    "no_progress_window": 2
  }
}
```

`expected_exit` stays 0. Drift detection treats every non-zero exit as red.

## Copying this into another repo

Copy `.cursor/skills/follow-the-loop/` and `.cursor/rules/follow-the-loop.mdc`. Install this package (or vendor `feature start`) so the scaffold command exists. Point the check command at that repo's oracle. Keep one unit per pack.

## Do not

- Add a second agent, a UI, or an embedding client as part of following this skill.
- Weaken tests to turn a red check green.
- Treat a feature pack as optional documentation after the code is written. The file comes first.
