"""Mission, current unit, pin, and gentle redirect.

Investigate chats stay quiet. A mission or unit arms the pin. A follow-up is
posted only when the open unit is abandoned or the loop says escalate.
New files are not off-track.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_QUESTION = re.compile(r"(?is)^\s*(why|what|how|where|when|who|which)\b")
_IMPERATIVE = re.compile(
    r"(?i)^\s*(ship|build|fix|implement|add|rename|write|create|make)\b"
)
_MISSION_LINE = re.compile(r"(?i)^\s*mission\s*:")
_UNIT_LINE = re.compile(r"(?i)^\s*(?:current|next)\s+unit\s*:\s*(.*)$")
_DROP = re.compile(r"(?i)actually drop that\.\s*(.+)")
_ABANDON = ("ignore the unit", "do not continue", "ignore the mission")
_DONE_CLAIM = re.compile(r"(?i)\b(all done|mission complete|task complete|we're done)\b")
_OTHER_WORK = re.compile(
    r"(?i)\b("
    r"i (wrote|created|built|added|shipped)|"
    r"database migration|migration instead|"
    r"homepage|marketing page|redesign|signup|"
    r"readme\.md|docs rewrite"
    r")\b"
)
_STOP = {
    "that",
    "this",
    "with",
    "from",
    "unit",
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
    """One conversation: investigate, then optional mission, then optional unit."""

    def __init__(self, conversation_id: str = "default") -> None:
        self.conversation_id = conversation_id
        self.phase = "investigate"
        self.mission: str | None = None
        self.unit: dict[str, Any] | None = None
        self.checks: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.prompts: list[str] = []
        self.last_assistant = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "phase": self.phase,
            "mission": self.mission,
            "unit": self.unit,
            "checks": self.checks,
            "events": self.events,
            "prompts": self.prompts,
            "last_assistant": self.last_assistant,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatCycle":
        cycle = cls(str(data.get("conversation_id") or "default"))
        cycle.phase = str(data.get("phase") or "investigate")
        cycle.mission = data.get("mission")
        cycle.unit = data.get("unit")
        cycle.checks = list(data.get("checks") or [])
        cycle.events = list(data.get("events") or [])
        cycle.prompts = list(data.get("prompts") or [])
        cycle.last_assistant = str(data.get("last_assistant") or "")
        return cycle

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path, conversation_id: str) -> "ChatCycle":
        if not path.is_file():
            return cls(conversation_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return cls(conversation_id)
        if not isinstance(data, dict):
            return cls(conversation_id)
        return cls.from_dict(data)

    def observe_user(self, text: str) -> None:
        raw = (text or "").strip()
        if not raw:
            return
        self.prompts.append(raw)
        drop = _DROP.search(raw)
        if drop and (self.unit or self.mission):
            self.start_unit(drop.group(1).strip(), done_means="", amended=True)
            return
        unit_line = _UNIT_LINE.match(raw)
        if unit_line:
            goal = unit_line.group(1).strip()
            if not self.mission:
                self.mission = goal
            self.start_unit(goal, done_means="", amended=bool(self.unit))
            return
        if _MISSION_LINE.match(raw):
            self.mission = raw
            self.phase = "unit" if self.unit else "mission"
            self.events.append({"action": "mission_set", "mission": raw})
            return
        if self.mission is None and self.phase == "investigate":
            if _QUESTION.match(raw) or raw.endswith("?"):
                return
            if _IMPERATIVE.match(raw):
                self.mission = raw
                self.phase = "mission"
                self.events.append({"action": "mission_set", "mission": raw})

    def start_unit(self, goal: str, done_means: str = "", *, amended: bool = False) -> None:
        goal = goal.strip()
        if not goal:
            return
        if not self.mission:
            self.mission = goal
        self.unit = {"goal": goal, "done_means": done_means.strip(), "status": "open"}
        self.phase = "unit"
        self.checks = []
        self.events.append(
            {
                "action": "unit_amended" if amended else "unit_started",
                "unit": goal,
                "done_means": done_means.strip(),
            }
        )

    def observe_tool(self, name: str, tool_input: Any = None, output: str = "") -> None:
        """Record the tool. Path novelty is not off-track."""
        self.events.append(
            {
                "action": "tool",
                "name": name,
                "input": tool_input if isinstance(tool_input, (dict, list, str, int, float, type(None))) else str(tool_input),
            }
        )
        if name.lower() == "shell" and isinstance(tool_input, dict):
            command = str(tool_input.get("command") or "")
            if "pytest" in command and output:
                exit_code = 0 if re.search(r"\bpassed\b", output) and "failed" not in output.lower() else 1
                self.record_check(exit_code, output)

    def record_check(self, exit_code: int, output: str = "") -> None:
        self.checks.append({"exit_code": int(exit_code), "output": output})

    def verdict(self) -> str:
        if not self.unit or not self.checks:
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
        if self.unit:
            lines.append("Unit: %s" % self.unit["goal"])
            if self.unit.get("done_means"):
                lines.append("Done when: %s" % self.unit["done_means"])
            lines.append("Verdict: %s" % self.verdict())
            lines.append("Answer only that unit.")
        else:
            lines.append("No unit yet.")
        return "\n".join(lines)

    def unit_words(self) -> set[str]:
        """Tokens from the open unit used to decide 'mentions unit'."""
        if not self.unit:
            return set()
        goal = self.unit["goal"].lower()
        goal_tokens = re.sub(r"[/\\._]+", " ", goal)
        words = {
            word
            for word in re.findall(r"[a-z][a-z0-9]{2,}", goal_tokens)
            if word not in _STOP and len(word) >= 3
        }
        words.update(re.findall(r"\b([a-z][a-z0-9_]{2,})\s*\(", goal))
        return words

    def explain_assistant(self, assistant: str) -> dict[str, Any]:
        """Why context-guard would silence or redirect on this assistant text.

        The *model* does not decide this — the product does, from the open unit
        and the assistant reply. User amend is a separate path (observe_user).
        """
        text = (assistant or "").strip()
        out: dict[str, Any] = {
            "phase": self.phase,
            "mission": self.mission,
            "unit": (self.unit or {}).get("goal"),
            "assistant_excerpt": text[:240],
            "action": "silence",
            "reason": "no open unit",
            "followup": None,
        }
        if not self.unit:
            return out
        if not text:
            out["reason"] = "empty assistant text"
            return out
        low = text.lower()
        words = self.unit_words()
        hits = sorted(word for word in words if word in low)
        other = _OTHER_WORK.search(text)
        out["unit_words"] = sorted(words)
        out["unit_word_hits"] = hits
        out["other_work_match"] = other.group(0) if other else None

        if any(cue in low for cue in _ABANDON):
            out["action"] = "redirect"
            out["reason"] = "assistant used an explicit abandon cue"
            out["kind"] = "model_sidetrack"
        elif _DONE_CLAIM.search(text) and self.verdict() != "pass":
            out["action"] = "redirect"
            out["reason"] = "done claim while unit check is not pass"
            out["kind"] = "model_sidetrack"
        elif words and not hits and other:
            out["action"] = "redirect"
            out["reason"] = (
                "assistant names other work (%s) and does not mention unit words %s"
                % (other.group(0), sorted(words))
            )
            out["kind"] = "model_sidetrack"
        elif self.verdict() == "escalate":
            out["action"] = "escalate"
            out["reason"] = "repeated failing checks"
            out["kind"] = "loop_escalate"
        elif hits and other:
            out["reason"] = (
                "other work mentioned but unit words still present (%s) — treat as on-unit"
                % hits
            )
            out["kind"] = "on_unit"
        else:
            out["reason"] = "on-unit (no abandon pattern)"
            out["kind"] = "on_unit"
        return out

    def abandoned(self, assistant: str) -> bool:
        return self.explain_assistant(assistant).get("action") == "redirect"

    def followup(self, assistant: str = "") -> str | None:
        if assistant:
            self.last_assistant = assistant
        if not self.unit:
            return None
        explained = self.explain_assistant(assistant or self.last_assistant)
        if explained.get("action") == "redirect":
            unit = self.unit["goal"].strip().rstrip(".")
            self.events.append({"action": "redirect", "unit": unit, "reason": explained.get("reason")})
            note = "[context-guard] Still the unit: %s. Continue only that." % unit
            explained["followup"] = note
            return note
        if explained.get("action") == "escalate" or self.verdict() == "escalate":
            note = "[context-guard] Stop and replan. Unit still: %s." % self.unit["goal"]
            explained["followup"] = note
            return note
        return None


def _prompt_from_payload(payload: dict[str, Any]) -> str:
    for key in ("prompt", "text", "message", "user_message", "agent_message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _ingest_transcript(cycle: ChatCycle, transcript_path: str | None) -> None:
    """Pull user prompts from Cursor's transcript when beforeSubmitPrompt was missed."""
    if not transcript_path or cycle.prompts:
        return
    path = Path(transcript_path)
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
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
        if text.strip():
            cycle.observe_user(text.strip())


def handle_hook(event: str, payload: dict[str, Any], root: Path) -> dict[str, Any]:
    """Cursor hook adapter. Returns the JSON object the hook should print."""
    conversation_id = str(payload.get("conversation_id") or payload.get("session_id") or "default")
    path = chat_path(root, conversation_id)
    cycle = ChatCycle.load(path, conversation_id)
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
        note = cycle.followup(cycle.last_assistant)
        cycle.save(path)
        if not note:
            return {}
        return {"followup_message": note}

    cycle.save(path)
    return {}
