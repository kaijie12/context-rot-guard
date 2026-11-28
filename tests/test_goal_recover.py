"""Feature: recover a living goal from an existing chat. No model calls."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from context_guard.cycle import ChatCycle, _recover_lines, chat_path, handle_hook
from context_guard.judge import ScriptedBootstrap, ScriptedJudge

ROOT = Path(__file__).resolve().parents[1]
GOAL = "Fix the exempt invoice so a $100 subtotal has $0 tax and totals $100"
CHECK = 'python3 -c "assert True"'
HOME = "a reseller certificate exempts only the home state"
MARKET = "a marketplace order is never exempt"
ON_GOAL = "The exempt invoice now returns $100 with $0 tax."


def _seed_prompts(cycle: ChatCycle) -> None:
    cycle.prompts.extend(
        [
            "Fix the exempt invoice so a $100 subtotal has $0 tax and totals $100.",
            "A reseller certificate exempts only the home state.",
            "A marketplace order is never exempt.",
        ]
    )


def test_recover_arms_from_scripted_bootstrap() -> None:
    cycle = ChatCycle(
        "recover-1",
        judge=ScriptedJudge("on_goal"),
        bootstrap=ScriptedBootstrap(GOAL, CHECK, [HOME, MARKET]),
    )
    _seed_prompts(cycle)
    assert cycle.show() == "No goal."

    cycle.observe_user("Recover goal")
    shown = cycle.show()
    assert GOAL in shown
    assert HOME in shown
    assert MARKET in shown
    assert "Still the goal" not in shown
    assert any(event.get("action") == "goal_recovered" for event in cycle.events)


def test_recover_keeps_later_details_when_a_slash_goal_exists() -> None:
    cycle = ChatCycle(
        "recover-details",
        bootstrap=ScriptedBootstrap(
            "Context-guard keeps a living goal and a check the program can fail",
            CHECK,
            [HOME, MARKET],
        ),
    )
    cycle.prompts.extend(
        [
            "/goal brainstorm whether an AI should judge the chat",
            "A reseller certificate exempts only the home state.",
            "A marketplace order is never exempt.",
            "Check: %s" % CHECK,
        ]
    )
    assert cycle.recover_from_prompts()
    shown = cycle.show()
    assert "brainstorm whether an AI" not in shown
    assert "living goal" in shown
    assert HOME in shown
    assert MARKET in shown
    assert CHECK in shown


def test_recover_buried_slash_goal_without_a_model() -> None:
    cycle = ChatCycle(
        "recover-a",
        bootstrap=ScriptedBootstrap(),  # empty — Layer A must win
    )
    wrapper = (
        "Skill Name: goal\nAccept `/goal <objective>`.\n"
        "<user_query>\n/goal %s\nCheck: %s\n</user_query>"
    ) % (GOAL, CHECK)
    cycle.prompts.append(wrapper)
    assert cycle.recover_from_prompts()
    shown = cycle.show()
    assert GOAL in shown
    assert CHECK in shown


def test_recover_with_empty_bootstrap_stays_no_goal() -> None:
    cycle = ChatCycle("recover-empty", bootstrap=ScriptedBootstrap())
    _seed_prompts(cycle)
    assert cycle.recover_from_prompts() is False
    assert cycle.show() == "No goal."


def test_hook_recover_then_green_stop_is_silent(tmp_path: Path) -> None:
    cid = "recover-hook"
    path = chat_path(tmp_path, cid)
    boot = ScriptedBootstrap(GOAL, CHECK, [HOME, MARKET])
    seed = ChatCycle(cid, judge=ScriptedJudge("on_goal"), bootstrap=boot)
    _seed_prompts(seed)
    seed.save(path)

    out = handle_hook(
        "beforeSubmitPrompt",
        {"conversation_id": cid, "prompt": "Recover goal"},
        tmp_path,
        judge=ScriptedJudge("on_goal"),
        bootstrap=boot,
    )
    assert out == {}
    shown = ChatCycle.load(path, cid).show()
    assert GOAL in shown
    assert HOME in shown
    assert MARKET in shown

    handle_hook(
        "afterAgentResponse",
        {"conversation_id": cid, "text": ON_GOAL},
        tmp_path,
        judge=ScriptedJudge("on_goal"),
        bootstrap=boot,
    )
    stop = handle_hook(
        "stop",
        {"conversation_id": cid, "status": "completed"},
        tmp_path,
        judge=ScriptedJudge("on_goal"),
        bootstrap=boot,
    )
    assert stop == {}


def test_cli_goal_show_after_recover(tmp_path: Path) -> None:
    cid = "recover-cli"
    cycle = ChatCycle(
        cid,
        bootstrap=ScriptedBootstrap(GOAL, "", [HOME, MARKET]),
    )
    _seed_prompts(cycle)
    cycle.recover_from_prompts()
    cycle.save(chat_path(tmp_path, cid))

    show = subprocess.run(
        [
            sys.executable,
            "-m",
            "context_guard",
            "goal",
            "show",
            "--conversation",
            cid,
            "--root",
            str(tmp_path),
        ],
        cwd=str(ROOT),
        env={**dict(**__import__("os").environ), "PYTHONPATH": str(ROOT / "src")},
        text=True,
        capture_output=True,
        check=False,
    )
    assert show.returncode == 0, show.stderr
    assert HOME in show.stdout
    assert MARKET in show.stdout


def test_recover_lines_keeps_middle_strips_guard_and_adds_cancel() -> None:
    early = "early phase: problem statement plan"
    middle = "middle phase: recover living goal"
    late = "late phase: grade the summary"
    pulse = (
        "Add a feature that runs context guard on the fly — continuously during a chat, "
        "not only at beforeSubmitPrompt and stop."
    )
    pin = (
        "[context-guard] The check is still open. Revamp and implement context-guard "
        "with continuous/on-the-fly pulses."
    )
    # Build more than 30 lines so a last-30 filter would drop the early/middle phases.
    bulk = ["noise line %s" % index for index in range(40)]
    lines = _recover_lines([early, middle] + bulk + [pulse, pin, late])
    assert early in lines
    assert middle in lines
    assert late in lines
    assert pulse in lines
    assert all(not line.lstrip().startswith("[context-guard]") for line in lines)
    assert any(
        "do not implement it" in line.lower() and "on-the-fly" in line.lower() for line in lines
    )


def test_show_renders_briefing_sections_after_recover() -> None:
    cycle = ChatCycle(
        "recover-briefing",
        bootstrap=ScriptedBootstrap(
            GOAL,
            CHECK,
            held=[HOME, MARKET],
            arc=["problem statement", "recover feature"],
            rejected=["continuous mid-chat pulse cancelled"],
            open_items=["grade the recover summary"],
        ),
    )
    _seed_prompts(cycle)
    assert cycle.recover_from_prompts()
    shown = cycle.show()
    assert "## Arc" in shown
    assert "## Held now" in shown
    assert "## Rejected / cancelled" in shown
    assert "## Open" in shown
    assert HOME in shown
    assert "mid-chat pulse" in shown
    pin = cycle.pin() or ""
    assert HOME in pin
    assert "## Arc" not in pin
    assert "## Rejected" not in pin


def test_fresh_goal_show_stays_flat_without_briefing_sections() -> None:
    cycle = ChatCycle("fresh-show")
    cycle.start_goal(GOAL, check=CHECK)
    cycle._add_detail(HOME)
    shown = cycle.show()
    assert "## Arc" not in shown
    assert "## Held now" not in shown
    assert shown.startswith(GOAL)
    assert "- %s" % HOME in shown


def test_unarmed_followup_stays_silent_when_briefing_sections_exist() -> None:
    cycle = ChatCycle(
        "loop-slim",
        judge=ScriptedJudge("on_goal"),
        bootstrap=ScriptedBootstrap(
            GOAL,
            CHECK,
            held=[HOME],
            arc=["early phase"],
            rejected=["cancelled pulse"],
            open_items=["grade still open"],
        ),
    )
    _seed_prompts(cycle)
    assert cycle.recover_from_prompts()
    note = cycle.followup(ON_GOAL)
    assert note is None
    assert cycle.loop_armed is False
    assert "## Arc" in cycle.show()
    assert "cancelled pulse" in cycle.show()
