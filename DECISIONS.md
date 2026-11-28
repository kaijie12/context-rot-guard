# Design decisions (v1)

Resolved before implementation, from `context-guard-plan.md` §3. Choices follow that spec’s MVP bias. Reopen them in this file before changing behavior.

| # | Decision | Choice | Why |
| --- | --- | --- | --- |
| D1 | Delivery form | **(d)** importable library + thin CLI | `ContextRotGuard` is the API. The CLI is a session file in front of it. |
| D2 | Language | **Python** | Fast to script; room for an embedding detector later. `requires-python >= 3.9` so this machine (3.9.6) can run it. Annotations use `from __future__ import annotations`. No 3.11-only stdlib. |
| D3 | Where it sits | **Message middleware** | `ContextRotGuard.process()` returns the message list. It does not run an agent. |
| D4 | Compaction trigger | **Both**, with opt-out | Compact when the raw window reaches `compact_every` turns **or** estimated tokens (`len // 4`) exceed `token_ceiling`. `enable_compact=False` / CLI `--no-compact` disables L1 entirely (including drift-forced compact) so Cursor/Claude can own summarization. Tool truncate, pin, anchor, and drift still run. |
| D5 | Who summarizes | **Extractive + template** | Digest is filled by pattern-matching dropped turns. `summarizer=` may rewrite done/open/risks in memory. **Goal text is copied from `GoalSpec` and restored after any summarizer.** No network call in v1. |
| D6 | Drift method | **Mechanical, Path B** | Verify stall, goal-mention gap, side-quest ratio, completion-without-green. `EmbeddingDriftDetector.score` raises `NotImplementedError`. |
| D7 | Embedding API | **None** | Path A is an interface stub only. |
| D8 | Thresholds | **Constructor knobs + defaults** | `compact_every=20`, `anchor_every=5`, `fail_streak=3`, `token_ceiling=8000`, `mention_gap=12`, `side_quest_ratio=0.6`. |
| D9 | On drift | **Soft warn + block synthetic done** | Drift adds a `[DRIFT]` system note and forces compact + anchor. `attempt_done()` returns `status=blocked` on drift, on a red check, or when no check exists. `--allow-done-on-red` is the only escape, and only for a red check while drift is false. |
| D10 | Persistence | **One JSON session file** | `.context-guard/session.json` (spec path). Turn history **and** the action event receipt (`events`, capped at 200) live in that file — not a separate JSONL log. Library use with no `session_path` stays in memory. CLI `log` prints the receipt; `quality-check` is the host-facing “should I trust this chat?” command (preview only — does not mark done). |
| D11 | Names | **`context-guard`** | Renamed from `context-rot-guard` / `context_rot_guard`. Console script `context-guard`. Import `context_guard`. Chat state lives under `.context-guard/chats/<id>.json`. Cursor hooks are `.cursor/hooks/guard-*.sh` (not `rot-*`). |
| D15 | Product | **Living goal + optional Open-list loop** | The goal stores the named sentence, optional `Check:` (docs / live runners only), later requirements (`details` / Held), and optional recover briefing lists (`arc`, `rejected`, `open`). `/goal …` and `Current goal: …` both arm it (including a Cursor-wrapped `/goal` prompt). `Recover goal` / `goal recover` scans all spoken user prompts (strip pasted `[context-guard]` pins; inject cancel-pulse evidence when missing) via one Composer bootstrap that returns a briefing JSON. `goal show` renders OVERARCHING + Arc / Held / Rejected / Open when those lists are set; the pin stays slim (mission, goal, check, Held only). **Guard:** a judge `off_goal` verdict posts one `Still the goal` redirect; on-track stops are silent. **Loop:** optional `/goal-loop` (off with `/goal-loop off`) arms an Open-list planner on stop — `Still open: …`, drop finished items, disarm when empty or `needs_plan`. The named shell Check does **not** drive stop follow-ups. |
| D16 | Product | **Grade the recover summary** | Quality of `goal show` after recover is a separate one-shot (Grok 4.7, medium reasoning, Fast off, 600s), not the Composer bootstrap that wrote it. The rubric is fixed in `features/recover_goal.feature` (briefing Shape allowed). The named check for that measurement is `examples/run_recover_grade_live.py`. Exit 0 is the measured pass. Pytest stays offline via `ScriptedGrader`. |

## Harness rails brought over

From `agent-sdlc/sample-harness-project` (Stage C guides/denies + Stage D closed loop), adapted for this repo:

| Sample piece | Here |
| --- | --- |
| `AGENTS.md` + `.cursor/rules/harness.mdc` | Same roles. Check command is `python3 -m pytest -q`. |
| `deny-rules.json`, `deny-read.js`, `deny-shell.js` | Same never-dos: `.env` / `secrets/`, force-push, prod mutate, `rm -rf /`. |
| `stop-check.sh` + `.claude/settings.example.json` | Stop runs **pytest**, not `pnpm typecheck`. Missing pytest skips (exit 0) so a bare checkout does not wedge the stop hook. |
| `sandbox.example.toml` | Same budget: ~15 minutes, 3 identical failures. |
| `TASK-PROMPT.example.md` | Closed-loop prompt pointed at this package’s pytest oracle. |
| Human gates | Kept the idea. This repo asks before a breaking `process()` / CLI change, a new required network dependency, or a package/script rename. Schema migrations and user-visible sends are not in v1, so those sample gates were not copied. |
| `src/username.js` oracle | Not copied. The oracle is `tests/`. Do not weaken tests to go green. |

## Non-decisions (still out of v1)

Embeddings, IDE plugins, multi-session orchestration, and running the coding agent itself. See README.
