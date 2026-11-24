# context-rot-guard

Long agent chats rot: the model forgets the goal, burns tokens on tool noise, and declares victory while checks fail. **context-rot-guard** is a small Python library and CLI that wraps the message list with three layers:

1. **Compress** old turns into a structured `SessionDigest` (extractive — no LLM call).
2. **Re-inject** the original goal and done-means as an authoritative anchor.
3. **Detect drift** when a verify command stalls, recent turns stop overlapping the goal, edits leave the allowlist, or the model says done while the last check is red.

It does not run an agent, and it does not guarantee the task succeeds. It keeps the *conversation* pointed at the mission you recorded at the start.

v1 decisions are in [`DECISIONS.md`](DECISIONS.md). The starting spec that produced this repo lives next to the prep notes as `ai-fde-prep/context-rot-guard-plan.md` (not in this package).

## Install and run

Python 3.9+ (3.11+ is the spec’s preferred line; this tree stays on the 3.9 standard library so a stock macOS `python3` can run it). No runtime dependencies.

```bash
cd context-rot-guard
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"

python -m pytest -q
python examples/demo_drift_session.py
```

`pip install -U pip` matters on older venvs (pip 21.x cannot editable-install a `pyproject.toml` project).

The demo needs nothing but the stdlib. Pytest is the only dev dependency. A checkout without pytest can still run the demo:

```bash
python3 examples/demo_drift_session.py
```

You should see `before_messages` / `after_messages`, `goal_verbatim=true`, and a `DRIFT drift=true` line. `done_status=blocked` because the fake checks stay red.

## CLI

The PyPI *project* name `ctxrot` is already taken (a DSPy context tool). This package’s console script is `context-rot-guard`. The same commands work via `python3 -m context_rot_guard`.

```bash
context-rot-guard init \
  --goal "Add max-length validation in src/username.js" \
  --done-means "pytest -q exits 0" \
  --constraint "do not edit tests" \
  --check-cmd "pytest -q"

context-rot-guard turn user "Add the length check."
context-rot-guard turn assistant "Implemented validation in src/username.js."
context-rot-guard check --exit-code 1 --log "FAILED tests/username.test.js"
context-rot-guard messages --json
context-rot-guard status
context-rot-guard done    # exit 2 while the last check is red or drift is set
```

State is written to `.context-rot-guard/session.json` in the current directory. Pass `--session` to put it somewhere else. `revise --goal "..."` replaces the mission and clears fail counters; it keeps the raw turns.

Library:

```python
from context_rot_guard import ContextRotGuard, GoalSpec

guard = ContextRotGuard(
    GoalSpec(
        goal="Add max-length validation in src/username.js",
        constraints=["do not edit tests"],
        done_means="pytest -q exits 0",
        check_cmd="pytest -q",
    ),
    compact_every=20,
    anchor_every=5,
    fail_streak=3,
)
guard.add_turn("user", "Add the length check.")
guard.record_check(1, "FAILED")
messages = guard.process()          # list to send to the model
report = guard.attempt_done()       # {"status": "blocked", ...} while verify is red
```

`process()` always starts with a pin (the digest, once compaction has run). It appends an anchor every `anchor_every` turns, on drift, and when called with `before_completion=True`. A red check also appends a correction (`meta.kind=correction`) for that unit only. Tool turns longer than 1200 characters are truncated, head and tail kept.

## New feature, same loop

Every feature starts the same way. The skill is [`.cursor/skills/follow-the-loop/SKILL.md`](.cursor/skills/follow-the-loop/SKILL.md). The always-on rule points at it. Scaffold the unit before writing product code:

```bash
context-rot-guard feature start \
  --slug export-api \
  --goal "Add a CSV export" \
  --done-means "pytest -q exits 0" \
  --check-cmd "pytest -q" \
  --allow-path src/context_rot_guard/export.py \
  --constraint "do not edit tests to force green"
```

That writes `.context-rot-guard/features/export-api/acceptance.json` and `BRIEF.md` (gitignored session state, regenerated per feature). `BRIEF.md` includes the `init` line. Pass `--max-check-attempts 3` and `--no-progress-window 2` on `init` when the session should stop and escalate instead of polishing a red check. Copy the skill folder into another repo to reuse the procedure; point `--check-cmd` at that repo's oracle.

Knobs (also CLI flags on `init`): `compact_every`, `anchor_every`, `fail_streak`, `token_ceiling`, `mention_gap`, `side_quest_ratio`. Token estimates are `len(text) // 4`.

## What drift means

| Signal | Fires when |
| --- | --- |
| `verify_stall` | The last `fail_streak` checks are all non-zero |
| `goal_mention_gap` | The last `mention_gap` turns share no keyword with the goal, constraints, or done-means |
| `side_quest` | At least three file paths show up in that window and ≥ 60% fall outside the allowlist (explicit `--allow-path` plus paths written in the goal) |
| `completion_without_green` | A recent assistant turn says done/finished while the last check is non-zero |

The sensor reads a short **intent ring** (last 24 snippets), not the compacted window, so folding old turns into a digest does not erase a stall. Path A (embeddings) is `EmbeddingDriftDetector.score`, which raises `NotImplementedError`.

A green check resets the fail streak. `attempt_done()` stays `blocked` on drift, on a red check, or when nothing has been recorded. `--allow-done-on-red` at `init` lets a red check through only when drift is false.

## How this differs

| Idea | What it covers | What this adds |
| --- | --- | --- |
| Aider `/clear` | Human drops the chat; conventions via `--read` | Automatic compact that **keeps the goal verbatim**, plus a drift sensor |
| Vendor thread compaction | Opaque summary of a long chat | Goal-anchored digest and check-command awareness |
| Goose `retry.checks` | Done means a shell exit code | Rolling re-injection of the mission across many turns |
| Cline `attempt_completion` | One-shot re-read of the task before done | Compression plus a fail streak, not a single prose check |
| Cursor rules / hooks | Guides and sensors on **tools** | Portable middleware any loop can call |
| Mem0-style memory | More stored context | Shrinks the window and pins the original mission |
| LangChain trim/summarize | Generic history management | Couples the pin to verify stall |
| PyPI `ctxrot` | DSPy context analytics | Not that package. Different project, no DSPy dependency |

## Harness rails

Developing *this* repo uses the Stage C / Stage D rails from the prep notes' `agent-sdlc/sample-harness-project`, retargeted at pytest.

| Rail | Role here |
| --- | --- |
| [`AGENTS.md`](AGENTS.md) | Check command, never-dos, human gates, 15-minute / 3-failure budget |
| [`.cursor/rules/harness.mdc`](.cursor/rules/harness.mdc) | Always-on pointer at `AGENTS.md` |
| [`deny-rules.json`](deny-rules.json) | Portable deny list |
| [`.cursor/hooks/deny-read.js`](.cursor/hooks/deny-read.js) | Block `.env*` and `secrets/` |
| [`.cursor/hooks/deny-shell.js`](.cursor/hooks/deny-shell.js) | Block force-push, prod mutate, `rm -rf /` |
| [`.cursor/hooks/stop-check.sh`](.cursor/hooks/stop-check.sh) | On stop, run pytest. Exit 1 blocks stop when pytest failed. Exit 0 if pytest is not installed |
| [`.claude/settings.example.json`](.claude/settings.example.json) | Same deny + stop shape for Claude Code |
| [`sandbox.example.toml`](sandbox.example.toml) | Illustrative sandbox and budget |
| [`TASK-PROMPT.example.md`](TASK-PROMPT.example.md) | Copy-paste closed-loop prompt |
| [`.cursor/skills/follow-the-loop/SKILL.md`](.cursor/skills/follow-the-loop/SKILL.md) | Procedure for every new feature |
| [`.cursor/rules/follow-the-loop.mdc`](.cursor/rules/follow-the-loop.mdc) | Always-on pointer at that skill |

Not brought over: the sample’s `src/username.js` red-test fixture (this package’s tests start green), `pnpm typecheck` as the stop oracle, and human gates for schema migrations or user-visible sends. Those do not apply to a library with no database and no outbound messaging. The product’s own “don’t say done while the check is red” rule is what `attempt_done()` enforces for sessions; `AGENTS.md` tells the coding agent not to bypass it.

## Non-goals (v1)

- IDE extension, published plugin, or a dashboard (the in-repo follow-the-loop skill is the setup, not a product surface)
- Real embedding drift
- Multi-agent or multi-session orchestration
- Driving Aider, Cline, Goose, or Cursor itself

## Status of the v1 bar

| Criterion | Where |
| --- | --- |
| Three layers in one run | `python3 examples/demo_drift_session.py` |
| Goal verbatim after a long compact | `tests/test_compress.py` |
| Fail streak sets `drift` with no embeddings | `tests/test_drift_mechanical.py` |
| `process()` documented | This README. Breaking changes bump the major version |
| Tests | `python3 -m pytest -q` |
| Honest scope | This section and the comparison table |
| Clone and run in a few minutes | Demo has zero dependencies |

## License

MIT. See [`LICENSE`](LICENSE).
