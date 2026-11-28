"""Decide on-goal vs off-goal by reading the reply.

Production uses CursorModelJudge (one Composer call, JSON verdict).
Tests pass ScriptedJudge or UnavailableJudge. There is no word list.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from typing import Any


class JudgeUnavailable(Exception):
    """The model judge did not return a verdict. Callers stay silent."""


class ScriptedJudge:
    """Test double. Optional substring map, otherwise one fixed verdict."""

    def __init__(
        self,
        verdict: str = "on_goal",
        when_contains: list[tuple[str, str]] | None = None,
    ) -> None:
        self._verdict = verdict
        self._when = list(when_contains or [])

    def judge(
        self,
        *,
        mission: str | None,
        goal: str,
        last_user: str,
        assistant: str,
    ) -> dict[str, str]:
        text = assistant or ""
        for needle, verdict in self._when:
            if needle.lower() in text.lower():
                return {"verdict": verdict, "reason": "scripted"}
        return {"verdict": self._verdict, "reason": "scripted"}


class ScriptedExtractor:
    """Test double for pulling a requirement out of a user line."""

    def __init__(
        self,
        rules: list[tuple[str, str, str]] | None = None,
        default: str = "ignore",
    ) -> None:
        self._rules = list(rules or [])
        self._default = default

    def extract(self, *, goal: str, details: list[str], text: str) -> dict[str, str]:
        raw = text or ""
        for needle, action, detail in self._rules:
            if needle.lower() in raw.lower():
                return {"action": action, "detail": detail}
        return {"action": self._default, "detail": ""}


class CursorModelExtractor:
    """One Composer call. add, drop, or ignore. Pytest never calls the model."""

    def extract(self, *, goal: str, details: list[str], text: str) -> dict[str, str]:
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return {"action": "ignore", "detail": ""}
        if not (os.environ.get("CURSOR_API_KEY") or "").strip():
            return {"action": "ignore", "detail": ""}
        prompt = _EXTRACT_PROMPT.format(
            goal=goal or "",
            details="\n".join("- %s" % item for item in details) or "(none)",
            text=text or "",
        )
        try:
            payload = _call_model_json(
                prompt,
                allowed=("add", "drop", "ignore"),
                field="action",
            )
        except JudgeUnavailable:
            return {"action": "ignore", "detail": ""}
        action = str(payload.get("action") or "ignore")
        if action not in {"add", "drop", "ignore"}:
            action = "ignore"
        return {"action": action, "detail": str(payload.get("detail") or "").strip()}


class ScriptedPlanner:
    """Test double for /goal-loop: continue, mark done, or request a plan."""

    def __init__(
        self,
        *,
        done_items: list[str] | None = None,
        plan_required: bool = False,
        plan: str = "",
        fail: bool = False,
    ) -> None:
        self._done = list(done_items or [])
        self._plan_required = plan_required
        self._plan = plan
        self._fail = fail
        self.calls: list[dict[str, Any]] = []

    def plan(
        self,
        *,
        goal: str,
        open_items: list[str],
        assistant: str,
        check_exit: int | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "goal": goal,
                "open_items": list(open_items),
                "assistant": assistant,
                "check_exit": check_exit,
            }
        )
        if self._fail:
            raise JudgeUnavailable("planner unavailable")
        if self._plan_required:
            return {"action": "needs_plan", "plan": self._plan, "done": []}
        return {"action": "continue", "done": list(self._done), "plan": ""}


class CursorModelPlanner:
    """One Composer call over goal + Open. Pytest / missing key → unavailable."""

    def plan(
        self,
        *,
        goal: str,
        open_items: list[str],
        assistant: str,
        check_exit: int | None = None,
    ) -> dict[str, Any]:
        del assistant, check_exit
        if os.environ.get("PYTEST_CURRENT_TEST"):
            raise JudgeUnavailable("planner unavailable under pytest")
        if not (os.environ.get("CURSOR_API_KEY") or "").strip():
            raise JudgeUnavailable("no CURSOR_API_KEY")
        joined = "\n".join("- %s" % item for item in open_items) or "(none)"
        prompt = _PLANNER_PROMPT.format(goal=goal, open_items=joined)
        try:
            payload = _call_model_object(prompt)
        except JudgeUnavailable:
            raise
        action = str(payload.get("action") or "").strip()
        if action not in {"continue", "needs_plan"}:
            raise JudgeUnavailable("planner action %r" % action)
        done = _bootstrap_string_list(payload.get("done"))
        return {
            "action": action,
            "done": done,
            "plan": str(payload.get("plan") or "").strip(),
        }


class ScriptedBootstrap:
    """Test double for recover: fixed goal, check, and briefing lists."""

    def __init__(
        self,
        goal: str = "",
        check: str = "",
        details: list[str] | None = None,
        *,
        arc: list[str] | None = None,
        held: list[str] | None = None,
        rejected: list[str] | None = None,
        open_items: list[str] | None = None,
    ) -> None:
        self._goal = goal
        self._check = check
        held_list = list(held if held is not None else (details or []))
        self._held = held_list
        self._arc = list(arc or [])
        self._rejected = list(rejected or [])
        self._open = list(open_items or [])

    def bootstrap(self, *, prompts: list[str]) -> dict[str, Any]:
        del prompts
        return {
            "goal": self._goal,
            "check": self._check,
            "held": list(self._held),
            "details": list(self._held),
            "arc": list(self._arc),
            "rejected": list(self._rejected),
            "open": list(self._open),
        }


RECOVER_RUBRIC = """\
Each item is pass or fail. The grade fails if any item fails.
- Goal. One durable ask for the whole chat. The latest complaint about /show-goal is not the goal.
- Coverage. Later rules that change the product are present: living goal from /goal, recover for an existing chat, silent when the check is green, one correction when the check is open or red, goal show lists held details, real subagent feature tests.
- Precision. Every detail is supported by a user message. A cancelled requirement belongs under Rejected / cancelled, not Held. The on-the-fly mid-chat pulse must not appear as work to build.
- Check. A Check: line only if the user named a command. python3 -m pytest -q may appear because it is this repo's named gate. No invented shell command.
- Shape. After recover on a long chat, the summary uses briefing sections (Arc, Held now, Rejected / cancelled, Open as needed). Held items are requirements, not a transcript dump and not system or skill text. Rejected may name cancelled work such as the mid-chat pulse.
"""


def _pulse_listed_as_work(goal_show: str) -> bool:
    """True when the summary tells the model to build the cancelled mid-chat pulse."""
    text = goal_show or ""
    lower = text.lower()
    if "pulse" not in lower:
        return False
    if "on-the-fly" not in lower and "on the fly" not in lower and "mid-chat" not in lower:
        return False
    for marker in ("do not add", "must not", "do not implement", "not work to build"):
        if marker in lower:
            return False
    # Pulse under Rejected / cancelled is evidence of withdrawal, not work to build.
    rejected_at = lower.find("## rejected")
    if rejected_at < 0:
        rejected_at = lower.find("rejected / cancelled")
    if rejected_at >= 0:
        rest = lower[rejected_at:]
        next_section = rest.find("\n## ", 3)
        window = rest if next_section < 0 else rest[:next_section]
        if "pulse" in window and (
            "on-the-fly" in window or "on the fly" in window or "mid-chat" in window
        ):
            return False
    return True


class ScriptedGrader:
    """Offline rubric. Fails a pulse built as work, and a summary that drops recover."""

    def grade(self, *, dialogue: list[str], goal_show: str, rubric: str) -> dict[str, Any]:
        del dialogue, rubric
        fails: list[str] = []
        show = goal_show or ""
        if _pulse_listed_as_work(show):
            fails.append("Precision")
        if "recover" not in show.lower():
            fails.append("Coverage")
        return {
            "pass": not fails,
            "fails": fails,
            "notes": "scripted",
            "raw": "",
            "prompt": "",
            "available": True,
        }


class CursorModelGrader:
    """One Grok 4.7 call, medium reasoning, Fast off. Not the bootstrap model."""

    model_id = "grok-4.7"

    def grade(self, *, dialogue: list[str], goal_show: str, rubric: str) -> dict[str, Any]:
        joined = "\n---\n".join(dialogue) if dialogue else "(none)"
        prompt = (
            _GRADE_PROMPT.replace("{rubric}", rubric or RECOVER_RUBRIC)
            .replace("{dialogue}", joined)
            .replace("{goal_show}", goal_show or "No goal.")
        )
        unavailable = {
            "pass": None,
            "fails": [],
            "notes": "unavailable",
            "raw": "",
            "prompt": prompt,
            "available": False,
            "model": self.model_id,
        }
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return unavailable
        if not (os.environ.get("CURSOR_API_KEY") or "").strip():
            unavailable["notes"] = "no CURSOR_API_KEY"
            return unavailable
        return self._grade_model(prompt, self.model_id)

    def _grade_model(self, prompt: str, model_id: str) -> dict[str, Any]:
        unavailable = {
            "pass": None,
            "fails": [],
            "notes": "unavailable",
            "raw": "",
            "prompt": prompt,
            "available": False,
            "model": model_id,
        }
        try:
            raw = _call_model_text(
                prompt,
                model_id=model_id,
                fast=False,
                extra_params=(("context", "256k"), ("reasoning_effort", "medium")),
                tools=(),
                timeout_s=600,
            )
            payload = _parse_json_object(raw)
        except JudgeUnavailable as exc:
            unavailable["notes"] = str(exc)
            return unavailable
        fails: list[str] = []
        raw_fails = payload.get("fails") or []
        if isinstance(raw_fails, list):
            for item in raw_fails:
                name = str(item or "").strip()
                if name and name not in fails:
                    fails.append(name)
        passed = payload.get("pass") is True and not fails
        return {
            "pass": passed,
            "fails": fails,
            "notes": str(payload.get("notes") or "").strip(),
            "raw": raw,
            "prompt": prompt,
            "available": True,
            "model": model_id,
        }


def _bootstrap_string_list(raw: Any) -> list[str]:
    out: list[str] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


class CursorModelBootstrap:
    """One Composer call over user prompts. Pytest / missing key → empty."""

    def bootstrap(self, *, prompts: list[str]) -> dict[str, Any]:
        empty: dict[str, Any] = {
            "goal": "",
            "check": "",
            "held": [],
            "details": [],
            "arc": [],
            "rejected": [],
            "open": [],
        }
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return empty
        if not (os.environ.get("CURSOR_API_KEY") or "").strip():
            return empty
        joined = "\n---\n".join(prompts) if prompts else "(none)"
        prompt = _BOOTSTRAP_PROMPT.format(prompts=joined)
        try:
            payload = _call_model_object(prompt)
        except JudgeUnavailable:
            return empty
        goal = str(payload.get("goal") or "").strip()
        check = str(payload.get("check") or "").strip()
        held_raw = payload.get("held")
        if held_raw is None:
            held_raw = payload.get("details") or []
        held = _bootstrap_string_list(held_raw)
        return {
            "goal": goal,
            "check": check,
            "held": held,
            "details": list(held),
            "arc": _bootstrap_string_list(payload.get("arc")),
            "rejected": _bootstrap_string_list(payload.get("rejected")),
            "open": _bootstrap_string_list(payload.get("open")),
        }


_EXTRACT_PROMPT = """\
You maintain a living goal for a coding chat.
Reply with JSON only, no markdown:
{{"action":"add"|"drop"|"ignore","detail":"one requirement sentence or empty"}}
Do not edit files. Do not call tools.

add: the user stated a new rule that changes how the goal must be built.
drop: the user withdrew a requirement that is already listed.
ignore: a question, a restatement, or color. Not a new requirement.

Goal: {goal}
Details already listed:
{details}
User text:
{text}
"""


class UnavailableJudge:
    def judge(
        self,
        *,
        mission: str | None,
        goal: str,
        last_user: str,
        assistant: str,
    ) -> dict[str, str]:
        raise JudgeUnavailable("judge unavailable")


_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)

_BOOTSTRAP_PROMPT = """\
You recover a living goal from an existing coding chat's USER messages only.
Read the whole list, not only the last /goal line.
Write a re-entry briefing, not a product brochure.
Reply with JSON only, no markdown:
{{"goal":"one overarching sentence","check":"shell command or empty","arc":["phase…"],"held":["standing rule…"],"rejected":["cancelled work…"],"open":["unfinished…"]}}
Do not edit files. Do not call tools.

goal: the durable ask across the whole thread. A complaint that /show-goal was thin is not the goal.
check: a program-evaluable command only if the user named one; else empty.
arc: real work phases in order (plans, features, recover, grade) with concrete names when the user named them.
held: standing rules that still bind the work. When the user asked for silent/invisible behavior, state both sides plainly: silent when the check is green; one correction (flag, realign, inform, and log) when the check is open or red. Also cover recover for old chats, live subagent tests, measure summary quality, and README docs. Include later rules even when an earlier /goal exists.
rejected: work the user withdrew (keyword brain, fake sidetracks, continuous mid-chat pulse when a later message cancels it). Put cancelled items here, never in held. Only mark the pulse cancelled when a user message says to stop or not implement it.
open: what is still unfinished or failing now.
Skip questions, restatements, tool chatter, and pasted [context-guard] blocks. Do not copy the transcript.

User messages (oldest first):
{prompts}
"""


_PLANNER_PROMPT = """\
You decide the next step for an optional goal-loop on a coding chat.
Reply with JSON only, no markdown:
{{"action":"continue"|"needs_plan","done":["finished open item…"],"plan":"short plan or empty"}}
Do not edit files. Do not call tools.

continue: keep working the remaining open items (or the goal if none are listed).
needs_plan: the next chunk needs a new plan from the user; put that ask in plan.
done: open items the assistant just finished; only list items that were open.

Goal: {goal}
Open items:
{open_items}
"""


_GRADE_PROMPT = """\
You grade a recovered living-goal summary. You did not write it.
Reply with JSON only, no markdown:
{"pass": true, "fails": [], "notes": "one sentence"}
Do not edit files. Do not call tools.

pass is true only when every rubric item passes.
fails lists the rubric item names that failed. Use only these names: Goal, Coverage, Precision, Check, Shape.

Rubric:
{rubric}

User dialogue (oldest first):
{dialogue}

Product goal show:
{goal_show}
"""


_PROMPT = """\
You judge one assistant reply against an open goal.
Reply with JSON only, no markdown:
{{"verdict":"on_goal"|"off_goal","reason":"one short sentence"}}
Do not edit files. Do not call tools. Do not write code.

on_goal: the reply is still doing that goal, including a necessary step of it.
off_goal: the reply switched to different work, even if it is the same product.

Mission: {mission}
Goal: {goal}
Last user line: {last_user}
Assistant reply:
{assistant}
"""


class CursorModelJudge:
    """One-shot Composer 2.5 judge. Fast off. Missing key or bad JSON is unavailable."""

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, str]] = {}

    def judge(
        self,
        *,
        mission: str | None,
        goal: str,
        last_user: str,
        assistant: str,
    ) -> dict[str, str]:
        # The default test suite must not call a model, even if a key is set.
        if os.environ.get("PYTEST_CURRENT_TEST"):
            raise JudgeUnavailable("pytest")
        key = hashlib.sha256(
            ("%s\n%s" % (goal or "", assistant or "")).encode("utf-8")
        ).hexdigest()
        cached = self._cache.get(key)
        if cached is not None:
            return dict(cached)
        try:
            verdict = _call_model(
                mission=mission or "",
                goal=goal or "",
                last_user=last_user or "",
                assistant=assistant or "",
            )
        except JudgeUnavailable:
            raise
        except Exception as exc:
            raise JudgeUnavailable(str(exc)) from exc
        self._cache[key] = verdict
        return dict(verdict)


def _call_model(*, mission: str, goal: str, last_user: str, assistant: str) -> dict[str, str]:
    prompt = _PROMPT.format(
        mission=mission,
        goal=goal,
        last_user=last_user,
        assistant=assistant,
    )
    payload = _call_model_json(prompt, allowed=("on_goal", "off_goal"), field="verdict")
    return {
        "verdict": str(payload["verdict"]),
        "reason": str(payload.get("reason") or payload["verdict"]),
    }


def _call_model_text(
    prompt: str,
    *,
    model_id: str = "composer-2.5",
    fast: bool = False,
    extra_params: tuple[tuple[str, str], ...] = (),
    tools: tuple[str, ...] | None = None,
    timeout_s: int = 300,
) -> str:
    if not (os.environ.get("CURSOR_API_KEY") or "").strip():
        raise JudgeUnavailable("no CURSOR_API_KEY")
    try:
        from cursor_sdk import (
            Agent,
            AgentOptions,
            LocalAgentOptions,
            ModelParameterValue,
            ModelSelection,
        )
    except ImportError as exc:
        raise JudgeUnavailable("cursor-sdk is not installed") from exc
    params_list = [ModelParameterValue(id=key, value=value) for key, value in extra_params]
    if fast:
        params_list.append(ModelParameterValue(id="fast", value="true"))
    elif extra_params:
        params_list.append(ModelParameterValue(id="fast", value="false"))
    # Isolated cwd so a model that ignores "do not edit files" cannot touch the repo.
    sandbox = tempfile.mkdtemp(prefix="context-guard-judge-")
    options = AgentOptions(
        api_key=os.environ["CURSOR_API_KEY"].strip(),
        model=ModelSelection(id=model_id, params=tuple(params_list)),
        local=LocalAgentOptions(cwd=sandbox),
        tools=None if tools is None else list(tools),
    )

    holder: dict[str, Any] = {}

    def _prompt() -> None:
        try:
            holder["result"] = Agent.prompt(prompt, options)
        except Exception as exc:
            holder["error"] = exc

    wait_s = max(30, int(timeout_s))
    thread = threading.Thread(target=_prompt, daemon=True)
    thread.start()
    thread.join(wait_s)
    if thread.is_alive():
        raise JudgeUnavailable("judge timed out after %ss" % wait_s)
    if "error" in holder:
        raise JudgeUnavailable(str(holder["error"])) from holder["error"]
    result = holder.get("result")
    status = str(getattr(result, "status", "") or "")
    text = str(getattr(result, "result", "") or "")
    if status and status.lower() not in {"finished", "completed", "success"} and not text.strip():
        code = str(getattr(result, "error_code", "") or "")
        message = str(getattr(result, "error_message", "") or "")
        detail = " ".join(part for part in (status, code, message) if part).strip()
        raise JudgeUnavailable("judge run status %s" % (detail or status))
    return text


def _call_model_object(
    prompt: str, *, model_id: str = "composer-2.5", fast: bool = False
) -> dict[str, Any]:
    return _parse_json_object(_call_model_text(prompt, model_id=model_id, fast=fast))


def _call_model_json(prompt: str, *, allowed: tuple[str, ...], field: str) -> dict[str, Any]:
    payload = _call_model_object(prompt)
    value = str(payload.get(field) or "")
    if value not in allowed:
        raise JudgeUnavailable("%s %r" % (field, value))
    return payload


def _parse_json_object(text: str) -> dict[str, Any]:
    match = _JSON_OBJECT.search(text or "")
    if not match:
        raise JudgeUnavailable("model returned no JSON")
    try:
        payload: Any = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise JudgeUnavailable("model JSON did not parse") from exc
    if not isinstance(payload, dict):
        raise JudgeUnavailable("model JSON was not an object")
    return payload
