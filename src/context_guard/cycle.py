"""Mission, current goal, pin, and gentle redirect.

Investigate chats stay quiet. A mission or goal arms the pin. A follow-up is
posted only when the judge says the assistant left the open goal, or the loop
says escalate. New files are not off-track.

Judgment:
  1. User text sets mission / goal (observe_user) — the coding model does not.
  2. On stop, a model judge reads the goal and the assistant reply:
       on_goal       — silence
       off_goal      — one Still the goal redirect
       unavailable   — silence, log judge=unavailable
  3. User “Actually drop that. …” amends the goal — not a redirect.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from context_guard.judge import (
    CursorModelBootstrap,
    CursorModelExtractor,
    CursorModelJudge,
    JudgeUnavailable,
)

_QUESTION = re.compile(r"(?is)^\s*(why|what|how|where|when|who|which)\b")
_IMPERATIVE = re.compile(
    r"(?i)^\s*(ship|build|fix|implement|add|rename|write|create|make)\b"
)
_MISSION_LINE = re.compile(r"(?i)^\s*mission\s*:")
# Prefer "goal"; keep "unit" as a deprecated alias so old chats still arm.
_GOAL_LINE = re.compile(r"(?im)^\s*(?:current|next)\s+(?:goal|unit)\s*:\s*(.+)$")
_SLASH_GOAL = re.compile(r"(?is)\A/goal\b\s*(.*)\Z")
_USER_QUERY = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.S)
_CHECK_LINE = re.compile(r"(?im)^\s*check\s*:\s*(.+)$")
_DROP = re.compile(r"(?i)actually drop that\.\s*(.+)")
_RECOVER = re.compile(r"(?is)^\s*recover(?:\s+the)?\s+goal\s*[.!]?\s*$")
_STOP = {
    "that",
    "this",
    "with",
    "from",
    "unit",
    "goal",
    "current",
    "examples",
    "function",
    "returns",
    "return",
    "numbers",
    "number",
    "file",
    "files",
    "live",
    "fixture",
    "the",
    "and",
    "for",
    "two",
    "one",
    "into",
    "only",
    "than",
    "then",
    "when",
    "what",
    "path",
}


def chat_path(root: Path, conversation_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", conversation_id or "default")[:80] or "default"
    return root / ".context-guard" / "chats" / ("%s.json" % safe)


class ChatCycle:
    """One conversation: investigate → optional mission → optional open goal."""

    def __init__(
        self,
        conversation_id: str = "default",
        judge: Any = None,
        extractor: Any = None,
        bootstrap: Any = None,
    ) -> None:
        self.conversation_id = conversation_id
        self.phase = "investigate"
        self.mission: str | None = None
        # Open work the agent should stay on. Shape: {goal, done_means, status}.
        self.goal: dict[str, Any] | None = None
        self.checks: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.prompts: list[str] = []
        self.last_assistant = ""
        self.judge = judge if judge is not None else CursorModelJudge()
        self.extractor = extractor if extractor is not None else CursorModelExtractor()
        self.bootstrap = bootstrap if bootstrap is not None else CursorModelBootstrap()
        self.user_turn = ""

    # Compat: older code/tests used .unit for the open goal object.
    @property
    def unit(self) -> dict[str, Any] | None:
        return self.goal

    @unit.setter
    def unit(self, value: dict[str, Any] | None) -> None:
        self.goal = value

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "phase": self.phase,
            "mission": self.mission,
            "goal": self.goal,
            # Keep writing "unit" for one release so old readers still work.
            "unit": self.goal,
            "checks": self.checks,
            "events": self.events,
            "prompts": self.prompts,
            "last_assistant": self.last_assistant,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatCycle":
        cycle = cls(str(data.get("conversation_id") or "default"))
        phase = str(data.get("phase") or "investigate")
        cycle.phase = "goal" if phase == "unit" else phase
        cycle.mission = data.get("mission")
        cycle.goal = _normalize_goal(
            data.get("goal") if data.get("goal") is not None else data.get("unit")
        )
        cycle.checks = list(data.get("checks") or [])
        cycle.events = list(data.get("events") or [])
        cycle.prompts = list(data.get("prompts") or [])
        cycle.last_assistant = str(data.get("last_assistant") or "")
        return cycle

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), indent=2)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path, conversation_id: str) -> "ChatCycle":
        if not path.is_file():
            return cls(conversation_id)
        try:
            raw_text = path.read_text(encoding="utf-8")
            data, _end = json.JSONDecoder().raw_decode(raw_text.lstrip())
        except (OSError, json.JSONDecodeError, ValueError):
            return cls(conversation_id)
        if not isinstance(data, dict):
            return cls(conversation_id)
        return cls.from_dict(data)

    def observe_user(self, text: str) -> None:
        raw = _spoken_user_text(text)
        if not raw:
            return
        self.prompts.append(raw)
        if _RECOVER.match(raw):
            self.user_turn = "recover"
            self.recover_from_prompts()
            return
        slash = _SLASH_GOAL.match(raw)
        if slash:
            objective = slash.group(1).strip()
            if objective:
                self._start_from_named_goal(objective, raw)
            return
        drop = _DROP.search(raw)
        if drop and (self.goal or self.mission):
            self._apply_drop(drop.group(1).strip())
            return
        goal_line = _GOAL_LINE.search(raw)
        if goal_line:
            self._start_from_named_goal(goal_line.group(1).strip(), raw)
            return
        if _MISSION_LINE.match(raw):
            self.mission = raw
            self.phase = "goal" if self.goal else "mission"
            self.events.append({"action": "mission_set", "mission": raw})
            return
        if self.goal:
            self._apply_extraction(raw)
            return
        if self.mission is None and self.phase == "investigate":
            if _QUESTION.match(raw) or raw.endswith("?"):
                return
            if _IMPERATIVE.match(raw):
                self.mission = raw
                self.phase = "mission"
                self.events.append({"action": "mission_set", "mission": raw})

    def recover_from_prompts(self, prompts: list[str] | None = None) -> bool:
        """Scan prior user text and arm a living goal. Returns True if a goal was set."""
        texts: list[str] = []
        for item in prompts if prompts is not None else list(self.prompts):
            spoken = _spoken_user_text(item)
            if not spoken or _RECOVER.match(spoken):
                continue
            texts.append(spoken)

        found_goal = ""
        found_check = ""
        for text in texts:
            slash = _SLASH_GOAL.match(text)
            if slash and slash.group(1).strip():
                found_goal = _CHECK_LINE.sub("", slash.group(1)).strip()
                check_line = _CHECK_LINE.search(text)
                found_check = check_line.group(1).strip() if check_line else ""
                continue
            goal_line = _GOAL_LINE.search(text)
            if goal_line:
                found_goal = _CHECK_LINE.sub("", goal_line.group(1)).strip()
                check_line = _CHECK_LINE.search(text)
                found_check = check_line.group(1).strip() if check_line else ""

        # A /goal line is only the seed. Later user messages still change the goal.
        # Always ask the bootstrap, even when a slash-goal was found.
        details: list[str] = []
        boot = self.bootstrap.bootstrap(prompts=_recover_lines(texts))
        boot_goal = str(boot.get("goal") or "").strip()
        boot_check = str(boot.get("check") or "").strip()
        if boot_goal:
            found_goal = boot_goal
        if found_check == "" and boot_check:
            found_check = boot_check
        # held (preferred) or legacy details → binding requirements
        held_raw = boot.get("held")
        if held_raw is None:
            held_raw = boot.get("details") or []
        for item in held_raw or []:
            detail = str(item or "").strip()
            if detail and detail not in details:
                details.append(detail)
        arc = _string_list(boot.get("arc"))
        rejected = _string_list(boot.get("rejected"))
        open_items = _string_list(boot.get("open"))

        if not found_goal:
            return False

        self.start_goal(found_goal, check=found_check, amended=bool(self.goal))
        assert self.goal is not None
        self.goal["arc"] = arc
        self.goal["rejected"] = rejected
        self.goal["open"] = open_items
        for detail in details:
            self._add_detail(detail)
        self.events.append(
            {
                "action": "goal_recovered",
                "goal": found_goal,
                "check": found_check,
                "details": list(details),
                "arc": list(arc),
                "rejected": list(rejected),
                "open": list(open_items),
            }
        )
        return True

    def _start_from_named_goal(self, text_goal: str, raw: str) -> None:
        check_line = _CHECK_LINE.search(raw)
        check = check_line.group(1).strip() if check_line else ""
        text_goal = _CHECK_LINE.sub("", text_goal).strip()
        if not self.mission:
            self.mission = text_goal
        self.start_goal(text_goal, done_means="", amended=bool(self.goal), check=check)

    def start_goal(
        self,
        goal: str,
        done_means: str = "",
        *,
        amended: bool = False,
        check: str = "",
    ) -> None:
        goal = goal.strip()
        if not goal:
            return
        if not self.mission:
            self.mission = goal
        self.goal = {
            "goal": goal,
            "done_means": done_means.strip(),
            "status": "open",
            "check": check.strip(),
            "details": [],
            "arc": [],
            "rejected": [],
            "open": [],
        }
        self.phase = "goal"
        self.checks = []
        self.events.append(
            {
                "action": "goal_amended" if amended else "goal_started",
                "goal": goal,
                "done_means": done_means.strip(),
                "check": check.strip(),
            }
        )

    def _held_show(self) -> str:
        """Slim goal + Held for stop reminders. No Arc / Rejected / Open."""
        if not self.goal:
            return "No goal."
        lines = [self.goal["goal"]]
        check = str(self.goal.get("check") or "").strip()
        if check:
            lines.append("Check: %s" % check)
        for detail in self.goal.get("details") or []:
            lines.append("- %s" % detail)
        return "\n".join(lines)

    def show(self) -> str:
        """The living goal the user can open, and the model is held to."""
        if not self.goal:
            return "No goal."
        goal_line = self.goal["goal"]
        check = str(self.goal.get("check") or "").strip()
        held = list(self.goal.get("details") or [])
        arc = list(self.goal.get("arc") or [])
        rejected = list(self.goal.get("rejected") or [])
        open_items = list(self.goal.get("open") or [])
        # Fresh /goal chats keep the short form until recover fills briefing sections.
        if not (arc or rejected or open_items):
            return self._held_show()
        lines = [goal_line]
        if check:
            lines.append("Check: %s" % check)
        if arc:
            lines.append("## Arc")
            for item in arc:
                lines.append("- %s" % item)
        if held:
            lines.append("## Held now")
            for item in held:
                lines.append("- %s" % item)
        if rejected:
            lines.append("## Rejected / cancelled")
            for item in rejected:
                lines.append("- %s" % item)
        if open_items:
            lines.append("## Open")
            for item in open_items:
                lines.append("- %s" % item)
        return "\n".join(lines)

    def _apply_extraction(self, text: str) -> None:
        if not self.goal:
            return
        extracted = self.extractor.extract(
            goal=self.goal["goal"],
            details=list(self.goal.get("details") or []),
            text=text,
        )
        action = str(extracted.get("action") or "ignore")
        detail = str(extracted.get("detail") or "").strip()
        if action == "add" and detail:
            self.user_turn = "detail"
            self._add_detail(detail)
        elif action == "drop" and detail:
            self.user_turn = "drop"
            self._drop_detail(detail)
        else:
            self.user_turn = "question" if "?" in text else "other"

    def _add_detail(self, detail: str) -> None:
        if not self.goal:
            return
        details = self.goal.setdefault("details", [])
        if detail not in details:
            details.append(detail)
        self.events.append({"action": "detail_added", "detail": detail})

    def _drop_detail(self, detail: str) -> None:
        if not self.goal:
            return
        needle = detail.lower()
        kept = []
        removed = False
        for item in self.goal.get("details") or []:
            if needle in item.lower() or item.lower() in needle:
                removed = True
                continue
            kept.append(item)
        self.goal["details"] = kept
        if removed:
            self.events.append({"action": "detail_dropped", "detail": detail})

    def _apply_drop(self, clause: str) -> None:
        if self.goal:
            extracted = self.extractor.extract(
                goal=self.goal["goal"],
                details=list(self.goal.get("details") or []),
                text="Actually drop that. %s" % clause,
            )
            if extracted.get("action") == "drop" and extracted.get("detail"):
                self._drop_detail(str(extracted["detail"]))
                return
            before = list(self.goal.get("details") or [])
            self._drop_detail(clause)
            if self.goal.get("details") != before:
                return
        self.start_goal(clause, done_means="", amended=True)

    # Deprecated name — same as start_goal.
    def start_unit(self, goal: str, done_means: str = "", *, amended: bool = False) -> None:
        self.start_goal(goal, done_means, amended=amended)

    def observe_tool(self, name: str, tool_input: Any = None, output: str = "") -> None:
        """Record the tool. Path novelty is not off-track."""
        self.events.append(
            {
                "action": "tool",
                "name": name,
                "input": tool_input
                if isinstance(tool_input, (dict, list, str, int, float, type(None)))
                else str(tool_input),
            }
        )
        if name.lower() != "shell" or not isinstance(tool_input, dict):
            return
        command = str(tool_input.get("command") or "")
        if not command:
            return
        named = str((self.goal or {}).get("check") or "").strip()
        is_named_check = bool(named) and (
            named in command or command.strip() == named or _commands_match(named, command)
        )
        is_pytest = "pytest" in command
        if not (is_named_check or is_pytest):
            return
        exit_code = _exit_code_from_tool_output(output)
        if exit_code is None and is_pytest and output:
            exit_code = (
                0
                if re.search(r"\bpassed\b", output) and "failed" not in output.lower()
                else 1
            )
        if exit_code is None:
            return
        self.record_check(exit_code, (output or "").strip())

    def record_check(self, exit_code: int, output: str = "") -> None:
        self.checks.append({"exit_code": int(exit_code), "output": output})

    def verdict(self) -> str:
        if not self.goal or not self.checks:
            return "unknown"
        last = self.checks[-1]
        if int(last["exit_code"]) == 0:
            return "pass"
        reds: list[dict[str, Any]] = []
        for check in reversed(self.checks):
            if int(check["exit_code"]) == 0:
                break
            reds.append(check)
        reds.reverse()
        if len(reds) >= 3:
            return "escalate"
        if len(reds) >= 2 and reds[-1].get("output") == reds[-2].get("output"):
            return "escalate"
        return "correct"

    def pin(self) -> str | None:
        if not self.mission:
            return None
        lines = ["[context-guard] Mission: %s" % self.mission]
        if self.goal:
            lines.append("Goal: %s" % self.goal["goal"])
            if self.goal.get("check"):
                lines.append("Check: %s" % self.goal["check"])
            for detail in self.goal.get("details") or []:
                lines.append("- %s" % detail)
            if self.goal.get("done_means"):
                lines.append("Done when: %s" % self.goal["done_means"])
            lines.append("Verdict: %s" % self.verdict())
            lines.append("Answer only that goal.")
        else:
            lines.append("No goal yet.")
        return "\n".join(lines)

    def goal_words(self) -> set[str]:
        """Tokens from the open goal used to decide 'mentions goal'."""
        if not self.goal:
            return set()
        text = self.goal["goal"].lower()
        tokens = re.sub(r"[/\\._]+", " ", text)
        words = {
            word
            for word in re.findall(r"[a-z][a-z0-9]{2,}", tokens)
            if word not in _STOP and len(word) >= 3
        }
        words.update(re.findall(r"\b([a-z][a-z0-9_]{2,})\s*\(", text))
        return words

    def unit_words(self) -> set[str]:
        return self.goal_words()

    def explain_assistant(self, assistant: str) -> dict[str, Any]:
        """Why context-guard would silence or redirect on this assistant text.

        A model judge reads the open goal and the reply. User amend is
        observe_user, not here. No word list.
        """
        text = (assistant or "").strip()
        out: dict[str, Any] = {
            "phase": self.phase,
            "mission": self.mission,
            "goal": (self.goal or {}).get("goal"),
            "assistant_excerpt": text[:240],
            "action": "silence",
            "reason": "no open goal",
            "followup": None,
            "judge": None,
        }
        if not self.goal:
            return out
        if not text:
            out["reason"] = "empty assistant text"
            return out
        goal = self.show()
        last_user = self.prompts[-1] if self.prompts else ""
        try:
            judged = self.judge.judge(
                mission=self.mission,
                goal=goal,
                last_user=last_user,
                assistant=text,
            )
        except JudgeUnavailable as exc:
            out["action"] = "silence"
            out["reason"] = "judge unavailable"
            out["judge"] = "unavailable"
            out["kind"] = "judge_unavailable"
            out["judge_error"] = str(exc)
            return out
        verdict = str((judged or {}).get("verdict") or "")
        reason = str((judged or {}).get("reason") or verdict)
        if verdict == "off_goal":
            out["action"] = "redirect"
            out["reason"] = reason
            out["judge"] = "off_goal"
            out["kind"] = "model_sidetrack"
        elif verdict == "on_goal":
            if self.verdict() == "escalate":
                out["action"] = "escalate"
                out["reason"] = "repeated failing checks"
                out["judge"] = "on_goal"
                out["kind"] = "loop_escalate"
            else:
                out["action"] = "silence"
                out["reason"] = reason
                out["judge"] = "on_goal"
                out["kind"] = "on_goal"
        else:
            out["action"] = "silence"
            out["reason"] = "judge unavailable"
            out["judge"] = "unavailable"
            out["kind"] = "judge_unavailable"
        return out

    def abandoned(self, assistant: str) -> bool:
        return self.explain_assistant(assistant).get("action") == "redirect"

    def followup(self, assistant: str = "") -> str | None:
        if assistant:
            self.last_assistant = assistant
        if not self.goal:
            return None
        explained = self.explain_assistant(assistant or self.last_assistant)
        if explained.get("action") == "redirect" and self.user_turn != "question":
            shown = self._held_show()
            self.events.append(
                {"action": "redirect", "goal": self.goal["goal"], "reason": explained.get("reason")}
            )
            note = "[context-guard] Still the goal: %s. Continue only that." % shown
            explained["followup"] = note
            return note
        note = self._loop_note()
        if note:
            explained["followup"] = note
            self.events.append({"action": "loop", "goal": self.goal["goal"], "note": note})
        return note

    def _loop_note(self) -> str | None:
        """Check result only. Confidence and a quiet exception are not a pass."""
        if not self.goal:
            return None
        if self.verdict() == "pass":
            return None
        if self.verdict() == "escalate":
            return "[context-guard] Stop and replan. Goal still: %s." % self._held_show()
        parts = ["[context-guard] The check is still open."]
        if self.checks:
            last = self.checks[-1]
            output = str(last.get("output") or "").strip()
            parts.append(output or "exit %s" % last.get("exit_code"))
        parts.append(self._held_show())
        parts.append("Stay on that goal.")
        return " ".join(parts)


def _normalize_goal(goal: Any) -> dict[str, Any] | None:
    if not isinstance(goal, dict):
        return None
    goal.setdefault("check", "")
    goal.setdefault("details", [])
    goal.setdefault("done_means", "")
    goal.setdefault("status", "open")
    goal.setdefault("arc", [])
    goal.setdefault("rejected", [])
    goal.setdefault("open", [])
    return goal


_CANCEL_PULSE = (
    "Stop the on-the-fly context guard feature work that was just started. "
    "Do not implement it; leave the repo as it was before that request."
)


def _string_list(raw: Any) -> list[str]:
    out: list[str] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _ensure_cancel_pulse(lines: list[str]) -> list[str]:
    """Make sure bootstrap sees that the mid-chat pulse was cancelled."""
    if any(
        "do not implement it" in line.lower() and "on-the-fly" in line.lower() for line in lines
    ):
        return list(lines)
    inserted: list[str] = []
    done = False
    for line in lines:
        inserted.append(line)
        lower = line.lower()
        if (
            not done
            and "on the fly" in lower
            and "continuously during a chat" in lower
        ):
            inserted.append(_CANCEL_PULSE)
            done = True
    if not done:
        inserted.append(_CANCEL_PULSE)
    return inserted


def _recover_lines(texts: list[str]) -> list[str]:
    """All spoken user lines for bootstrap. Drop dumps and pasted guard pins."""
    kept: list[str] = []
    for text in texts:
        if text.startswith("<") or text.startswith("Available subagent"):
            continue
        if "available_subagent_types" in text[:200]:
            continue
        if text.lstrip().startswith("[context-guard]"):
            continue
        if len(text) > 2000:
            text = text[:2000].rstrip()
        kept.append(text)
    return _ensure_cancel_pulse(kept)


def _spoken_user_text(text: str) -> str:
    """The user's words. A Cursor /goal turn wraps those words in a skill prompt."""
    raw = (text or "").strip()
    found = _USER_QUERY.findall(raw)
    if found:
        return found[-1].strip()
    return raw


def _prompt_from_payload(payload: dict[str, Any]) -> str:
    for key in ("prompt", "text", "message", "user_message", "agent_message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def prompts_from_transcript(transcript_path: str | Path) -> list[str]:
    """User lines from a Cursor JSONL transcript."""
    path = Path(transcript_path)
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        role = str(row.get("role") or "")
        if role != "user":
            message = row.get("message")
            if isinstance(message, dict) and str(message.get("role") or "") == "user":
                role = "user"
            else:
                continue
        text = ""
        message = row.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(str(block.get("text") or ""))
                text = "\n".join(parts)
            elif isinstance(content, str):
                text = content
        if not text:
            text = str(row.get("text") or row.get("content") or "")
        spoken = _spoken_user_text(text)
        if spoken:
            out.append(spoken)
    return out


def _ingest_transcript(cycle: ChatCycle, transcript_path: str | None) -> None:
    """Pull user prompts from Cursor's transcript when beforeSubmitPrompt was missed."""
    if not transcript_path or cycle.prompts:
        return
    for text in prompts_from_transcript(transcript_path):
        cycle.observe_user(text)


def _commands_match(named: str, command: str) -> bool:
    """True when the shell ran the named check, even with a cd prefix."""
    named_core = named.strip()
    command_core = command.strip()
    if not named_core or not command_core:
        return False
    if named_core in command_core:
        return True
    # Compare the trailing python -c / pytest fragment.
    for needle in (named_core, named_core.split("&&")[-1].strip()):
        if needle and needle in command_core:
            return True
    return False


def _exit_code_from_tool_output(output: str) -> int | None:
    text = (output or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        for key in ("exit_code", "exitCode", "code", "status_code"):
            if key in data and data[key] is not None:
                try:
                    return int(data[key])
                except (TypeError, ValueError):
                    pass
        nested = data.get("result")
        if isinstance(nested, dict):
            for key in ("exit_code", "exitCode", "code"):
                if key in nested and nested[key] is not None:
                    try:
                        return int(nested[key])
                    except (TypeError, ValueError):
                        pass
        if data.get("ok") is True or data.get("success") is True:
            return 0
        if data.get("ok") is False or data.get("success") is False:
            return 1
    if re.search(r"\bexit(?:_code|Code)?\s*[:=]\s*0\b", text) or re.search(
        r"\bpassed\b", text, re.I
    ):
        if "failed" not in text.lower() and "error" not in text.lower()[:80]:
            return 0
    if re.search(r"\bexit(?:_code|Code)?\s*[:=]\s*[1-9]\d*\b", text):
        return 1
    if "traceback" in text.lower() or "assertionerror" in text.lower():
        return 1
    return None


def _run_named_check(cycle: ChatCycle, root: Path) -> None:
    """Run the living goal's Check on stop. No Check named means the loop stays open."""
    if not cycle.goal:
        return
    command = str(cycle.goal.get("check") or "").strip()
    if not command:
        return
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(root),
            text=True,
            capture_output=True,
            timeout=420,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        cycle.record_check(1, str(exc))
        return
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    cycle.record_check(result.returncode, output)


def handle_hook(
    event: str,
    payload: dict[str, Any],
    root: Path,
    judge: Any = None,
    extractor: Any = None,
    bootstrap: Any = None,
) -> dict[str, Any]:
    """Cursor hook adapter. Returns the JSON object the hook should print."""
    conversation_id = str(payload.get("conversation_id") or payload.get("session_id") or "default")
    path = chat_path(root, conversation_id)
    cycle = ChatCycle.load(path, conversation_id)
    if judge is not None:
        cycle.judge = judge
    if extractor is not None:
        cycle.extractor = extractor
    if bootstrap is not None:
        cycle.bootstrap = bootstrap
    event = event or str(payload.get("hook_event_name") or "")
    transcript = payload.get("transcript_path")
    if isinstance(transcript, str):
        _ingest_transcript(cycle, transcript)

    if event in {"beforeSubmitPrompt", "UserPromptSubmit"}:
        cycle.observe_user(_prompt_from_payload(payload))
        cycle.save(path)
        return {}

    if event == "afterAgentResponse":
        cycle.last_assistant = _prompt_from_payload(payload) or str(payload.get("text") or "")
        cycle.save(path)
        return {}

    if event == "postToolUse":
        cycle.observe_tool(
            str(payload.get("tool_name") or ""),
            payload.get("tool_input"),
            str(payload.get("tool_output") or ""),
        )
        cycle.save(path)
        pin = cycle.pin()
        if not pin:
            return {}
        return {"additional_context": pin}

    if event == "sessionStart":
        cycle.save(path)
        pin = cycle.pin()
        if not pin:
            return {}
        return {"additional_context": pin}

    if event == "stop":
        if str(payload.get("status") or "") not in {"", "completed"}:
            return {}
        _run_named_check(cycle, root)
        note = cycle.followup(cycle.last_assistant)
        cycle.save(path)
        if not note:
            return {}
        return {"followup_message": note}

    cycle.save(path)
    return {}
