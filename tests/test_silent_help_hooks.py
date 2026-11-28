"""Silent help through the real hook path. No model calls."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from context_guard.cycle import ChatCycle, chat_path, handle_hook
from context_guard.judge import ScriptedExtractor, ScriptedJudge

ROOT = Path(__file__).resolve().parents[1]
GOAL = "Fix the exempt invoice so a $100 subtotal has $0 tax and totals $100"
CHECK = 'python3 -c "assert True"'
HOME = "a reseller certificate exempts only the home state"
ON_GOAL = "The exempt invoice now returns $100 with $0 tax."
CID = "silent-help"


def _slash_prompt(goal: str = GOAL, check: str = CHECK) -> str:
    return (
        "Skill Name: goal\nAccept `/goal <objective>`.\n"
        "<user_query>\n/goal %s\nCheck: %s\n</user_query>"
    ) % (goal, check)


def test_hook_slash_goal_detail_check_and_stop_are_silent(tmp_path: Path) -> None:
    judge = ScriptedJudge("on_goal")
    extractor = ScriptedExtractor([("reseller certificate", "add", HOME)])

    armed = handle_hook(
        "beforeSubmitPrompt",
        {"conversation_id": CID, "prompt": _slash_prompt()},
        tmp_path,
        judge=judge,
        extractor=extractor,
    )
    assert armed == {}

    cycle = ChatCycle.load(chat_path(tmp_path, CID), CID)
    shown = cycle.show()
    assert GOAL in shown
    assert CHECK in shown

    detail = handle_hook(
        "beforeSubmitPrompt",
        {
            "conversation_id": CID,
            "prompt": "A reseller certificate exempts only the home state.",
        },
        tmp_path,
        judge=judge,
        extractor=extractor,
    )
    assert detail == {}
    cycle = ChatCycle.load(chat_path(tmp_path, CID), CID)
    assert HOME in cycle.show()

    pin = handle_hook(
        "postToolUse",
        {
            "conversation_id": CID,
            "tool_name": "Shell",
            "tool_input": {"command": "cd /tmp && %s" % CHECK},
            "tool_output": json.dumps({"exit_code": 0, "stdout": "passed"}),
        },
        tmp_path,
        judge=judge,
        extractor=extractor,
    )
    assert "followup_message" not in pin
    assert GOAL in (pin.get("additional_context") or "")
    assert HOME in (pin.get("additional_context") or "")

    handle_hook(
        "afterAgentResponse",
        {"conversation_id": CID, "text": ON_GOAL},
        tmp_path,
        judge=judge,
        extractor=extractor,
    )
    stop = handle_hook(
        "stop",
        {"conversation_id": CID, "status": "completed"},
        tmp_path,
        judge=judge,
        extractor=extractor,
    )
    assert stop == {}

    show = subprocess.run(
        [
            sys.executable,
            "-m",
            "context_guard",
            "goal",
            "show",
            "--conversation",
            CID,
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
    assert GOAL in show.stdout
    assert CHECK in show.stdout
    assert HOME in show.stdout


def test_hook_stop_speaks_when_no_check_was_named(tmp_path: Path) -> None:
    judge = ScriptedJudge("on_goal")
    handle_hook(
        "beforeSubmitPrompt",
        {
            "conversation_id": "open-check",
            "prompt": (
                "Skill Name: goal\n"
                "<user_query>\n/goal %s\n</user_query>" % GOAL
            ),
        },
        tmp_path,
        judge=judge,
    )
    handle_hook(
        "afterAgentResponse",
        {"conversation_id": "open-check", "text": ON_GOAL},
        tmp_path,
        judge=judge,
    )
    stop = handle_hook(
        "stop",
        {"conversation_id": "open-check", "status": "completed"},
        tmp_path,
        judge=judge,
    )
    assert stop == {}
    note = stop.get("followup_message") or ""
    assert "check is still open" not in note.lower()
    assert "Still the goal" not in note


def test_hook_stop_stays_silent_when_on_goal_without_goal_loop(tmp_path: Path) -> None:
    judge = ScriptedJudge("on_goal")
    handle_hook(
        "beforeSubmitPrompt",
        {"conversation_id": "auto-check", "prompt": _slash_prompt()},
        tmp_path,
        judge=judge,
    )
    handle_hook(
        "afterAgentResponse",
        {"conversation_id": "auto-check", "text": ON_GOAL},
        tmp_path,
        judge=judge,
    )
    stop = handle_hook(
        "stop",
        {"conversation_id": "auto-check", "status": "completed"},
        tmp_path,
        judge=judge,
    )
    assert stop == {}
    cycle = ChatCycle.load(chat_path(tmp_path, "auto-check"), "auto-check")
    assert cycle.loop_armed is False


def test_hook_stop_redirects_once_on_off_goal(tmp_path: Path) -> None:
    judge = ScriptedJudge("off_goal")
    handle_hook(
        "beforeSubmitPrompt",
        {"conversation_id": "off", "prompt": _slash_prompt()},
        tmp_path,
        judge=judge,
    )
    handle_hook(
        "postToolUse",
        {
            "conversation_id": "off",
            "tool_name": "Shell",
            "tool_input": {"command": CHECK},
            "tool_output": json.dumps({"exit_code": 0}),
        },
        tmp_path,
        judge=judge,
    )
    handle_hook(
        "afterAgentResponse",
        {"conversation_id": "off", "text": "Rewrote the pricing homepage instead."},
        tmp_path,
        judge=judge,
    )
    stop = handle_hook(
        "stop",
        {"conversation_id": "off", "status": "completed"},
        tmp_path,
        judge=judge,
    )
    note = stop.get("followup_message") or ""
    assert "Still the goal" in note
    assert GOAL in note


def test_hook_without_a_goal_stays_silent(tmp_path: Path) -> None:
    handle_hook(
        "beforeSubmitPrompt",
        {"conversation_id": "plain", "prompt": "why is login failing?"},
        tmp_path,
    )
    stop = handle_hook(
        "stop",
        {"conversation_id": "plain", "status": "completed"},
        tmp_path,
    )
    assert stop == {}
