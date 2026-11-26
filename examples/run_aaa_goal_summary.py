#!/usr/bin/env python3
"""Ask Grok 4.7 for an AAA goal show after a full read of this chat's user lines.

This is not the grader. It writes the aspirational summary: goal sentence,
optional Check, and key details. The product recover summary is printed beside
it when available.

Needs: Python >= 3.10, cursor-sdk, CURSOR_API_KEY.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_guard.cycle import (  # noqa: E402
    ChatCycle,
    _spoken_user_text,
    chat_path,
)
from context_guard.judge import (  # noqa: E402
    RECOVER_RUBRIC,
    JudgeUnavailable,
    _call_model_text,
    _parse_json_object,
)

CID = "e0957c65-48ed-4aff-918c-70de1f6b2124"
_ZSHRC_KEY = __import__("re").compile(
    r"""^\s*(?:export\s+)?CURSOR_API_KEY\s*=\s*(['\"]?)([^'\"\n]+)\1\s*$""",
    __import__("re").MULTILINE,
)
CANCEL = (
    "Stop the on-the-fly context guard feature work that was just started. "
    "Do not implement it; leave the repo as it was before that request."
)
OUT_JSON = ROOT / "examples" / "live-aaa-goal-summary.json"
OUT_MD = ROOT / "examples" / "LAST_AAA_GOAL_SUMMARY.md"
PRODUCT_DIFF = ROOT / "examples" / "LAST_SUMMARY_DIFF.md"

_AAA_PROMPT = """\
You do a full read of this coding chat's USER messages.
Write a grade-AAA briefing someone can open mid-chat to know what this long conversation has been doing.
Reply with JSON only, no markdown:
{"goal_show":"OVERARCHING GOAL\\nCheck: command or omit\\n## Arc\\n- phase or decision\\n## Held now\\n- requirement still true\\n## Rejected / cancelled\\n- thing dropped\\n## Open\\n- what is still unfinished","notes":"one sentence on why this arms a reader for this chat"}
Do not edit files. Do not call tools.

This is not a product brochure and not a restatement of the marketing thesis alone.
A valuable summary for THIS chat must answer:
1) Overarching goal: what the user has been trying to make true across the whole thread.
2) Arc: the real work phases in order (plans, features, recover, grade, loop complaints), with names of plans/files when the user named them.
3) Held now: standing rules that still bind the work (silent green, one correction on open/red, recover for old chats, live subagent tests, measure summary quality).
4) Rejected / cancelled: keyword brain, fake sidetracks, continuous mid-chat pulse if cancelled, and anything else the user withdrew.
5) Open: what is still unfinished or failing right now (e.g. recover summary quality, grade check).

Do not flatten the chat into six generic product bullets.
Do not treat a pasted [context-guard] block as a new user requirement.
Do not invent work the user did not ask for.
Prefer concrete nouns from the dialogue (plan names, feature files, /show-goal, recover, grade runner) over abstract slogans.

Rubric (quality bar, not the outline to copy):
{rubric}

User dialogue (oldest first, full list for this run):
{dialogue}
"""


def maybe_reexec_venv() -> None:
    if sys.version_info >= (3, 10):
        return
    venv_py = ROOT / ".venv" / "bin" / "python"
    if not venv_py.is_file():
        return
    os.execv(str(venv_py), [str(venv_py), str(Path(__file__).resolve()), *sys.argv[1:]])


def ensure_api_key() -> str | None:
    key = (os.environ.get("CURSOR_API_KEY") or "").strip()
    if key:
        return key
    path = Path.home() / ".zshrc"
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = _ZSHRC_KEY.search(text)
    if not match:
        return None
    value = (match.group(2) or "").strip()
    if value:
        os.environ["CURSOR_API_KEY"] = value
    return value or None


def spoken_prompts_from_sidecar() -> list[str]:
    cycle = ChatCycle.load(chat_path(ROOT, CID), CID)
    out: list[str] = []
    for item in cycle.prompts:
        spoken = _spoken_user_text(item)
        if not spoken:
            continue
        if spoken.startswith("<") or spoken.startswith("Available subagent"):
            continue
        if "available_subagent_types" in spoken[:200]:
            continue
        if len(spoken) > 2000:
            spoken = spoken[:2000].rstrip()
        out.append(spoken)
    return out


def with_cancel(lines: list[str]) -> list[str]:
    if any("do not implement it" in line.lower() and "on-the-fly" in line.lower() for line in lines):
        return list(lines)
    inserted: list[str] = []
    done = False
    for line in lines:
        inserted.append(line)
        if (
            not done
            and "on the fly" in line.lower()
            and "continuously during a chat" in line.lower()
        ):
            inserted.append(CANCEL)
            done = True
    if not done:
        inserted.append(CANCEL)
    return inserted


def product_from_diff() -> str:
    if not PRODUCT_DIFF.is_file():
        return ""
    text = PRODUCT_DIFF.read_text(encoding="utf-8")
    start = text.find("## Product (Composer bootstrap recover)")
    end = text.find("## Grok verifier")
    if start < 0:
        return ""
    block = text[start:end if end > start else None]
    lines = block.splitlines()[1:]
    return "\n".join(lines).strip()


def main() -> int:
    maybe_reexec_venv()
    os.environ.pop("PYTEST_CURRENT_TEST", None)
    if not ensure_api_key():
        print("no CURSOR_API_KEY", file=sys.stderr)
        return 1

    dialogue = with_cancel(spoken_prompts_from_sidecar())
    if len(dialogue) < 10:
        fixture = json.loads(
            (ROOT / "examples" / "fixtures" / "recover_this_chat_users.json").read_text(
                encoding="utf-8"
            )
        )
        dialogue = with_cancel(
            [str(x) for x in (fixture.get("lines") or []) if str(x).strip()]
        )

    print("dialogue_lines", len(dialogue), flush=True)
    prompt = _AAA_PROMPT.replace("{rubric}", RECOVER_RUBRIC).replace(
        "{dialogue}", "\n---\n".join(dialogue)
    )
    print(
        "Asking Grok 4.7 medium for an AAA chat briefing (up to 10 minutes)...",
        flush=True,
    )
    try:
        raw = _call_model_text(
            prompt,
            model_id="grok-4.7",
            fast=False,
            extra_params=(("context", "256k"), ("reasoning_effort", "medium")),
            tools=(),
            timeout_s=600,
        )
        payload = _parse_json_object(raw)
        aaa = str(payload.get("goal_show") or "").strip()
        notes = str(payload.get("notes") or "").strip()
        available = True
    except JudgeUnavailable as exc:
        raw = ""
        aaa = ""
        notes = str(exc)
        available = False
        print("GROK_UNAVAILABLE", exc, flush=True)

    product = product_from_diff()
    if not product:
        print("Recovering product summary for the side-by-side...", flush=True)
        cycle = ChatCycle("aaa-product")
        cycle.recover_from_prompts(dialogue)
        product = cycle.show()

    record = {
        "written_at": datetime.now(timezone.utc).isoformat(),
        "conversation_id": CID,
        "dialogue_lines": len(dialogue),
        "dialogue": dialogue,
        "product_goal_show": product,
        "aaa_goal_show": aaa,
        "notes": notes,
        "available": available,
        "model": "grok-4.7",
        "reasoning_effort": "medium",
        "raw": raw,
    }
    OUT_JSON.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUT_MD.write_text(
        "\n".join(
            [
                "# AAA chat briefing vs product",
                "",
                "Grok 4.7 medium did a full read and wrote a re-entry briefing for this chat,",
                "not a product brochure. Dialogue lines: %s." % len(dialogue),
                "",
                "## Product (Composer recover)",
                "",
                product or "(empty)",
                "",
                "## AAA briefing (Grok full read)",
                "",
                aaa or "(empty)",
                "",
                "## Notes",
                "",
                notes or "(none)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print("\n## Product (Composer recover)\n", flush=True)
    print(product or "(empty)", flush=True)
    print("\n## AAA (Grok full read)\n", flush=True)
    print(aaa or "(empty)", flush=True)
    print("\n## Notes\n", flush=True)
    print(notes or "(none)", flush=True)
    return 0 if available and aaa else 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
