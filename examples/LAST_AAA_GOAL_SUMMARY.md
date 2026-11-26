# AAA chat briefing vs product

Grok 4.7 medium did a full read and wrote a re-entry briefing for this chat,
not a product brochure. Dialogue lines: 155.

## Product (Composer recover)

Revamp context-guard so it almost invisibly keeps every chat on a living, expanding goal (from /goal and recoverable for existing chats), realigns when work drifts or stops short, verifies via loop/judge with silent green results, exposes the held goal and key details (/show-goal), ships per the problem statement and revamp plans with real subagent feature tests, and defines measurable quality for recovered/summary goals before going further.
- Stay user-friendly and almost invisible: silent on green/on-track; only flag rot, realign, inform, and log when action is needed.
- Analyze the full chat, not only the last /goal line, to judge on-track status and to expand and maintain key requirements added later in the thread.
- Treat stopping short of fully completing the goal as the main failure mode rather than assuming sidetrack unless the user causes it; loop verifies and can push completion.
- Keep loop in the architecture/diagram; explain and implement how the loop functions with the judge and cycle.
- Arm a living goal from /goal via beforeSubmitPrompt; run the named check on stop; support continuous on-the-fly pulses (event- or periodic-driven) that re-run check and judge as new details arrive.
- For existing chats without prior guard setup, scan the whole conversation and recover goal plus held details from USER messages only.
- /show-goal must reflect the whole chat with sufficient detail; support multiple conversations; document official usage (/goal, skills, readme).
- Use problem_statement plan as the TTD/feature base; follow revamp_living_goal plan to rebuild the repo; include a concrete implementation plan, not design docs only.
- Feature tests must use a real live subagent—no fake or stubbed model responses for sidetrack or recovery scenarios.
- Implement in src/context_guard/ (cycle, judge, cli, hooks) and wire through .cursor/skills/; verify end-to-end flow and guard state under dot-context-guard chats.
- Add a feature skill to print the summary context goal of the chat.
- Provide visibility into actual chat transcripts (full request/response) where the product uses or summarizes chats.
- Before moving forward on recover goal, define how to measure summary quality: run the product on a real chat (e.g. this one), produce the product response, a rubric, and an external model that scores product output against the full chat dialogue (recover_goal.feature / grade_recover_summary plan).
- Context guard should silently help in every chat per the problem statement.

## AAA briefing (Grok full read)

OVERARCHING GOAL
Make context-guard (renamed from context-rot-guard) actually keep a chat on a living goal: AI reads the thread against that goal, holds details added later, realigns when work stops short or truly drifts, stays quiet while on track, and can show the held goal. It has to work for a new chat and for a chat that never had the guard, be proven with live subagent feature tests, and stay small enough to share as an AI-engineer interview theory project.
## Arc
- Verified ai-fde-prep/context-rot-guard-plan.md against the repo. The aim was detect drift from the intended goal, share a small theory project, and surface AI-engineer knowledge gaps.
- Chose almost invisible over a skill the user must remember: flag rot, realign, inform, and log when needed. Questioned Compress versus Cursor and shadow middleware; asked parallel subagents to validate ideas and pick a top 3. Scope: every chat, Cursor or Claude, small and useful.
- Untangled on_turn / on_verify / on_done versus a quality check, and whether the agent or the user runs it. Asked for a plan, challenged the success criteria, then said go ahead. README, an in-chat try, GitHub PR 2, merge PRs, pull, then revert that pull so a doubtful loop commit and merge conflicts could come out before a new PR.
- The in-chat run still felt manual. Drift signals were too weak and hooks felt non-transferable. Rework order: which context is read, what the chat goal is, whether the chat is doing the job, voice the goal, and pair it with the loop (PR 2).
- Renamed to context-guard. Off-track means leaving the main goal; a red check should be rare. Guard alone is half a product: it must flex as a large task changes and cycle with loop. Asked if developers actually face this.
- BDD in plain feature language: a subagent does a real task, the chat is sidetracked, the product brings it back. drift_from_scratch_d666b475.plan.md combines loop and context-guard. Muted the hook. A first message may be an investigation, not a mission. Ran that plan. README had to say plainly what the tool does.
- Test storytelling: logs, prompt versus product decision, then a two-lane diagram (messages on the left, product on the right). Parked a mission keyword in favor of /goal. Tests had to be a realistic build plus a sidetrack, with verifiers. One primary feature file. Live model on every run of features/stay_on_unit.feature (shell key so the run could happen; Fast only if it is actually the cheap tier). Run until pass, PR, formatting, more logs, a sent / replied / context-guard table, then hook cleanup before merging that PR.
- Stopped calling the scenario a unit. examples/LAST_LIVE_TRANSCRIPT.md (math work, then a marketing turn) never showed where [context-guard] redirected, including on a subagent. User located the brain at src/context_guard/cycle.py and rejected a keyword search.
- New /goal: a real guard where AI judges the chat against the goal. Problem deep-dive first; drop the add(a, b) example. User sidetrack is the guard case; loop is the model stopping short of done. Zero fake model replies. Clear problem statement for both.
- Guard also expands the goal with later key details so work is not redone, and the user can view that goal anytime. Loop stays on the diagram. problem_statement_36ca25b0.plan.md is the feature base; revamp_living_goal_81ac8910.plan.md rebuilds the repo and must run a real subagent. User said build the problem statement, the revamp, and the implementation. Wanted the full live transcript, not a trimmed log.
- Added a skill and /show-goal. It showed no goal; it must handle multiple conversations, and the README must document /goal. Asked for the end-to-end path: beforeSubmitPrompt arms the living goal, the named check runs on stop, green stays silent, plus judge, cycle, and goal show, and for this chat's own guard state.
- A continuous mid-chat pulse was requested, then stopped with the repo left as it was. The follow-on ask was recover_living_goal_03186d38.plan.md: scan an existing chat that never had the guard, with a live subagent feature. Built. /show-goal still missed most of the chat.
- Quality moved to features/recover_goal.feature: product summary, a rubric, an external model scoring it against the full dialogue (this chat is allowed). grade_recover_summary_9b551e96.plan.md. User could not see what the grade run did, asked why it failed, and asked for the product summary beside the grok verifier summary, then a full-read grade-AAA summary to aim at.
## Held now
- Living goal is armed from /goal through beforeSubmitPrompt. The named check runs on stop. A green check stays silent. One correction when the check is open or red: flag, realign, inform, and log only then.
- The goal expands with requirements and key details added later. /show-goal lists the held goal and those details. Multiple conversations work. The README documents /goal, the skills, and official use.
- An existing chat with no prior guard is recovered by scanning the whole conversation, USER messages only, into a goal plus held details (recover_living_goal_03186d38.plan.md, features/recover_goal.feature, live subagent).
- Loop verifies and pushes when the model stops short of done. Context-guard keeps the goal in sight and redirects real drift. Off-track means leaving the main goal, and a large task may change.
- The judgment is an AI read of the chat against the goal (cycle and judge), not keywords.
- Feature tests call a live subagent on every run. No stubbed model replies. Scenario language is goal or mission; the live file is still features/stay_on_unit.feature.
- Summary quality is measured on features/recover_goal.feature: product output, a rubric, and an external model against the real full dialogue (grade_recover_summary_9b551e96.plan.md).
- Useful on every chat. Small enough to share. The first message may be an investigation.
## Rejected / cancelled
- Keyword-search brain in the decision path.
- Fake or scripted model replies, including a planted sidetrack that left a bug for nearby billing work, and the add(a, b) example.
- The continuous mid-chat pulse that would re-run the check and judge during a chat. Stopped before implementation; the repo was to stay as it was. That pulse is not work to build.
- The word unit for the scenario. The mission keyword was parked; /goal is the trigger.
- Hook chatter on a clean result, after mute the hook, including a no-drift line on every turn.
- Weak non-AI drift signals, and an off-track label used for anything other than leaving the main goal.
## Open
- Recovered /show-goal is failing the recover_living_goal_03186d38.plan.md bar: too thin, does not encapsulate the whole chat. Why is still being debugged.
- grade_recover_summary_9b551e96.plan.md: the grade run is unclear and failed. Still need the product goal summary and the grok verifier summary side by side, and why they differ.
- features/recover_goal.feature has no trusted quality measure yet (product output, rubric, external model on the full dialogue).
- A full-read grade-AAA goal summary is the bar the product summary should reach. The product output is not there.

## Notes

A mid-chat reader can separate the durable living-goal product from the named plans, see that the keyword brain, fake sidetracks, and mid-chat pulse are dead, and treat the live failure as recover /show-goal quality plus the grade check.
