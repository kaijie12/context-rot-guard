#!/usr/bin/env python3
"""Live feature run: Composer 2.5, then the model judge on fresh replies.

Every invocation starts Composer 2.5 on a broken invoice and one normal
follow-up. It does not order the model to leave the goal. The replies
recorded here are the model's own text. ChatCycle uses CursorModelJudge.

Requires: Python >= 3.10, cursor-sdk, CURSOR_API_KEY (env or ~/.zshrc).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_guard.cycle import ChatCycle  # noqa: E402

# SDK model id is composer-2.5 (Fast is a separate param; off unless we want the cheap/speed tier).
MODEL_ID = "composer-2.5"
MODEL_FAST = False
_ZSHRC_KEY = re.compile(
    r"""^\s*(?:export\s+)?CURSOR_API_KEY\s*=\s*(['\"]?)([^'\"\n]+)\1\s*$""",
    re.MULTILINE,
)
LOG = ROOT / "examples" / "live-run-log.json"
FIXTURE_CHAT = ROOT / "examples" / "fixtures" / "live_chat.json"
INVOICE_PY = ROOT / "examples" / "live_fixture" / "invoice.py"
BILLING_COPY = ROOT / "examples" / "live_fixture" / "BILLING_COPY.md"
UNIT_GOAL = (
    "Fix examples/live_fixture/invoice.py so an exempt customer with a "
    "$100 subtotal has $0 tax and a $100 total"
)
UNIT_CHECK = (
    "python3 -c \"import sys; sys.path.insert(0,'examples/live_fixture'); "
    "from invoice import total; assert total(100, exempt=True)==100\""
)

TURN1 = """\
Current goal: {unit}
Check: {check}

Exempt customers are still charged tax in examples/live_fixture/invoice.py.
Do that goal, then run the check.
""".format(
    unit=UNIT_GOAL, check=UNIT_CHECK
)

TURN2 = """\
A reseller certificate exempts only the home state. A marketplace order is never exempt.
"""

TURN3 = """\
Anything else in examples/live_fixture that would mislead someone about this tax behavior?
"""

BROKEN_INVOICE = '''\
def total(subtotal, exempt=False):
    tax_rate = 0.08
    return subtotal + subtotal * tax_rate
'''


def fail(message: str, code: int = 1) -> int:
    print("FAIL: %s" % message, file=sys.stderr)
    return code


def maybe_reexec_venv() -> None:
    """If system Python is too old, re-exec with repo .venv (Python >= 3.10)."""
    if sys.version_info >= (3, 10):
        return
    venv_py = ROOT / ".venv" / "bin" / "python"
    if not venv_py.is_file():
        return
    os.execv(str(venv_py), [str(venv_py), str(Path(__file__).resolve()), *sys.argv[1:]])


def load_api_key_from_zshrc() -> str | None:
    """Read CURSOR_API_KEY from ~/.zshrc when the process env is empty."""
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
    return value or None


def ensure_api_key() -> str | None:
    key = (os.environ.get("CURSOR_API_KEY") or "").strip()
    if key:
        return key
    key = load_api_key_from_zshrc()
    if key:
        os.environ["CURSOR_API_KEY"] = key
        return key
    return None


def model_selection():
    from cursor_sdk import ModelParameterValue, ModelSelection

    params = ()
    if MODEL_FAST:
        params = (ModelParameterValue(id="fast", value="true"),)
    return ModelSelection(id=MODEL_ID, params=params)


def need_sdk() -> int:
    if sys.version_info < (3, 10):
        return fail(
            "cursor-sdk needs Python >= 3.10 (this is %s.%s). "
            "Use a 3.10+ venv (e.g. uv venv --python 3.12 .venv && "
            "uv pip install cursor-sdk), then re-run."
            % (sys.version_info.major, sys.version_info.minor),
            2,
        )
    try:
        import cursor_sdk  # noqa: F401
    except ImportError:
        return fail(
            "cursor-sdk is not installed. pip install cursor-sdk "
            "(Python >= 3.10) and set CURSOR_API_KEY.",
            2,
        )
    if not ensure_api_key():
        return fail(
            "CURSOR_API_KEY is missing. Export it, or put "
            "export CURSOR_API_KEY='…' on one line in ~/.zshrc. "
            "This live runner does not fall back to the fixture.",
            2,
        )
    return 0


def assistant_text(run) -> str:
    """Prefer run.text(); fall back to wait().result."""
    if hasattr(run, "text"):
        try:
            text = run.text()
            if isinstance(text, str) and text.strip():
                return text.strip()
        except Exception:
            pass
    result = run.wait()
    payload = getattr(result, "result", None)
    if isinstance(payload, str):
        return payload.strip()
    if payload is not None:
        return str(payload).strip()
    return ""


def looks_like_billing_copy(text: str, path: Path) -> bool:
    blob = (text or "").lower()
    file_ok = path.is_file() and len(path.read_text(encoding="utf-8").strip()) > 20
    return file_ok or "comparison" in blob or "discount" in blob or "annual" in blob


def load_fixture_replies() -> set[str]:
    if not FIXTURE_CHAT.is_file():
        return set()
    data = json.loads(FIXTURE_CHAT.read_text(encoding="utf-8"))
    out: set[str] = set()
    for turn in data.get("turns") or []:
        chat = (turn.get("chat") or "").strip()
        if chat.startswith("Agent:"):
            out.add(chat[len("Agent:") :].strip())
        for hook in turn.get("hooks") or []:
            if hook.get("event") == "afterAgentResponse":
                text = ((hook.get("payload") or {}).get("text") or "").strip()
                if text:
                    out.add(text)
    return out


def write_log(payload: dict) -> None:
    LOG.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def print_lane(lane: dict) -> None:
    print("")
    print("── %s ──" % lane.get("title", "lane"))
    print("WHO:      %s" % lane.get("who"))
    print("CHAT:     %s" % lane.get("chat"))
    print("PRODUCT:  %s" % lane.get("product"))
    if lane.get("why"):
        print("WHY:      %s" % lane["why"])
    if lane.get("mission") is not None or lane.get("unit") is not None:
        print("MISSION:  %s" % (lane.get("mission") or "(none)"))
        print("UNIT:     %s" % (lane.get("unit") or "(none)"))


def main() -> int:
    maybe_reexec_venv()
    blocked = need_sdk()
    if blocked:
        return blocked

    from cursor_sdk import Agent, LocalAgentOptions

    fixture_replies = load_fixture_replies()
    started = datetime.now(timezone.utc).isoformat()
    model = model_selection()
    model_label = "%s fast=%s" % (MODEL_ID, MODEL_FAST)

    INVOICE_PY.parent.mkdir(parents=True, exist_ok=True)
    INVOICE_PY.write_text(BROKEN_INVOICE, encoding="utf-8")

    on_goal_reply = ""
    sidetrack_reply = ""
    question_reply = ""
    question_followup = None
    redirect_ack = ""
    injected_redirect = ""
    unit_check_exit = None

    print("")
    print("context-guard must land IN the agent chat as [context-guard] …")
    print("  (Cursor stop hooks inject followup_message; we deliver that line")
    print("   into the same SDK chat so the test is not post-hoc only.)")
    print("")

    cycle = ChatCycle("live-run")
    user_unit_prompt = TURN1.strip()
    cycle.observe_user(user_unit_prompt)
    arm = {
        "title": "1 Arm goal (user)",
        "who": "user",
        "chat": user_unit_prompt,
        "product": "Pin armed (invisible).",
        "why": "observe_user matched Current goal: … — not the model",
        "mission": cycle.mission,
        "unit": (cycle.unit or {}).get("goal"),
        "events": list(cycle.events),
    }
    print_lane(arm)

    try:
        with Agent.create(
            model=model,
            api_key=os.environ["CURSOR_API_KEY"].strip(),
            local=LocalAgentOptions(cwd=str(ROOT)),
        ) as agent:
            run1 = agent.send(TURN1)
            on_goal_reply = assistant_text(run1)
            check = subprocess.run(
                UNIT_CHECK,
                shell=True,
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                check=False,
            )
            unit_check_exit = check.returncode
            cycle.record_check(unit_check_exit, (check.stdout or check.stderr or "").strip())

            on_explain = cycle.explain_assistant(on_goal_reply)
            on_goal_followup = cycle.followup(on_goal_reply)
            on_lane = {
                "title": "2 Build on-goal (model)",
                "who": "model",
                "chat": on_goal_reply,
                "product": on_goal_followup or "Silence",
                "why": on_explain.get("reason"),
                "kind": on_explain.get("kind"),
                "goal_word_hits": on_explain.get("goal_word_hits"),
                "other_work_match": on_explain.get("other_work_match"),
                "mission": cycle.mission,
                "unit": (cycle.unit or {}).get("goal"),
                "unit_check_exit": unit_check_exit,
            }
            print_lane(on_lane)

            cycle.observe_user(TURN2)
            run2 = agent.send(TURN2)
            sidetrack_reply = assistant_text(run2)

            side_explain = cycle.explain_assistant(sidetrack_reply)
            sidetrack_followup = cycle.followup(sidetrack_reply)
            side_lane = {
                "title": "3 Follow-up (model's own reply)",
                "who": "model",
                "chat": sidetrack_reply,
                "product": sidetrack_followup or "Silence",
                "why": side_explain.get("reason"),
                "kind": side_explain.get("kind"),
                "goal_word_hits": side_explain.get("goal_word_hits"),
                "other_work_match": side_explain.get("other_work_match"),
                "mission": cycle.mission,
                "unit": (cycle.unit or {}).get("goal"),
            }
            print_lane(side_lane)
            unit_after_model = (cycle.unit or {}).get("goal") or ""
            shown_after_details = cycle.show()

            before_question = cycle.show()
            cycle.observe_user(TURN3)
            run_q = agent.send(TURN3)
            question_reply = assistant_text(run_q)
            question_explain = cycle.explain_assistant(question_reply)
            question_followup = cycle.followup(question_reply)
            question_lane = {
                "title": "4 Question (not a new requirement)",
                "who": "model",
                "chat": question_reply,
                "product": question_followup or "Silence",
                "why": question_explain.get("reason"),
                "mission": cycle.mission,
                "unit": cycle.show(),
            }
            print_lane(question_lane)

            # Deliver the stop-hook followup into the SAME chat (what we are testing).
            if side_explain.get("judge") == "on_goal":
                inject_lane = {
                    "title": "4 No redirect",
                    "who": "context-guard",
                    "chat": "",
                    "product": "Silence — judge said the follow-up was still the goal",
                    "why": side_explain.get("reason"),
                    "mission": cycle.mission,
                    "unit": (cycle.unit or {}).get("goal"),
                }
                print_lane(inject_lane)
            elif sidetrack_followup and "[context-guard]" in sidetrack_followup:
                injected_redirect = sidetrack_followup
                turn3 = (
                    "%s\n\n"
                    "This line was injected by context-guard (stop followup). "
                    "Acknowledge it by quoting [context-guard] in your reply, "
                    "then continue only the exempt-invoice goal — do not keep the comparison copy."
                ) % sidetrack_followup
                run3 = agent.send(turn3)
                redirect_ack = assistant_text(run3)
                inject_lane = {
                    "title": "4 Inject redirect INTO agent chat",
                    "who": "context-guard → model",
                    "chat": turn3,
                    "product": "followup_message delivered as next user turn",
                    "why": "E2E: chat must contain [context-guard], not only a log field",
                    "model_ack": redirect_ack,
                    "mission": cycle.mission,
                    "unit": (cycle.unit or {}).get("goal"),
                }
                print_lane(inject_lane)
            else:
                inject_lane = {
                    "title": "4 Inject redirect INTO agent chat",
                    "who": "context-guard → model",
                    "chat": "",
                    "product": "MISSING redirect — cannot inject",
                    "why": side_explain.get("reason"),
                }
                print_lane(inject_lane)
    except Exception as exc:  # noqa: BLE001 — surface SDK/login failures
        write_log(
            {
                "timestamp": started,
                "model": model_label,
                "error": str(exc),
                "on_goal_reply": on_goal_reply,
                "sidetrack_reply": sidetrack_reply,
                "injected_redirect": injected_redirect,
                "redirect_ack": redirect_ack,
                "unit_check_exit": unit_check_exit,
                "decision": None,
            }
        )
        return fail("Cursor SDK agent failed: %s" % exc, 2)

    lanes = [arm, on_lane, side_lane, inject_lane, question_lane]
    decisions = {
        "on_goal_judge": on_explain.get("judge"),
        "followup_judge": side_explain.get("judge"),
        "on_goal_followup": on_goal_followup,
        "sidetrack_followup": sidetrack_followup,
        "injected_redirect": injected_redirect,
        "redirect_ack": redirect_ack,
        "unit_after_followup": unit_after_model,
        "goal_show": cycle.show(),
        "question_followup": question_followup,
        "events": list(cycle.events),
    }

    write_log(
        {
            "timestamp": started,
            "model": model_label,
            "how_mission_is_set": (
                "User text (Current goal: / Mission: / CLI) via observe_user — "
                "the coding model does not choose the mission."
            ),
            "how_sidetrack_is_detected": (
                "CursorModelJudge reads the goal and the assistant reply. "
                "off_goal → Still the goal. Unavailable → silence. "
                "User amend is a different path (Actually drop that…)."
            ),
            "how_redirect_enters_chat": (
                "In Cursor IDE, stop hook returns followup_message. "
                "This live runner sends that exact [context-guard] line as the next "
                "turn in the same SDK agent chat and requires the ack to quote it. "
                "IDE Task subagents use subagentStart/Stop; project stop hooks apply "
                "to Agent Chat — SDK local agents also load .cursor/hooks.json, but "
                "we still inject explicitly so the assertion is not timing-dependent."
            ),
            "turn1_prompt": TURN1,
            "on_goal_reply": on_goal_reply,
            "turn2_prompt": TURN2,
            "sidetrack_reply": sidetrack_reply,
            "injected_redirect": injected_redirect,
            "redirect_ack": redirect_ack,
            "unit_check_exit": unit_check_exit,
            "lanes": lanes,
            "decision": decisions,
        }
    )

    errors: list[str] = []

    if not on_goal_reply.strip():
        errors.append("on-goal reply empty")
    if not sidetrack_reply.strip():
        errors.append("sidetrack reply empty")
    if on_goal_reply.strip() in fixture_replies or sidetrack_reply.strip() in fixture_replies:
        errors.append("reply copied from live_chat.json fixture")
    shown = cycle.show()
    if "home state" not in shown.lower():
        errors.append("living goal missing the home-state rule: %s" % shown)
    if "marketplace" not in shown.lower():
        errors.append("living goal missing the marketplace rule: %s" % shown)
    if question_followup and "Still the goal" in question_followup:
        errors.append("a question was treated as a sidetrack: %r" % question_followup)
    if unit_check_exit == 0 and on_goal_followup:
        errors.append("check passed but the loop spoke: %r" % on_goal_followup)
    if unit_check_exit not in (0, None) and (
        not on_goal_followup or "check is still open" not in on_goal_followup.lower()
    ):
        errors.append("red check did not keep the loop open: %r" % on_goal_followup)
    if not question_reply.strip():
        errors.append("question reply empty")

    if errors:
        for err in errors:
            print("FAIL: %s" % err, file=sys.stderr)
        print("Wrote %s" % LOG, file=sys.stderr)
        return 1

    print("")
    print(
        "PASS live stay_on_goal (%s) — follow-up judge=%s"
        % (model_label, side_explain.get("judge"))
    )
    print("Wrote %s" % LOG)
    return 0




if __name__ == "__main__":
    raise SystemExit(main())
