#!/usr/bin/env python3
"""Live recover: seed a chat with no living goal, then Recover goal on Composer.

Layer A cannot win (no Current goal: / leading /goal). CursorModelBootstrap
must arm the goal. Then one SDK agent turn stays on that goal; a green check
keeps followup silent.

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

MODEL_ID = "composer-2.5"
MODEL_FAST = False
_ZSHRC_KEY = re.compile(
    r"""^\s*(?:export\s+)?CURSOR_API_KEY\s*=\s*(['\"]?)([^'\"\n]+)\1\s*$""",
    re.MULTILINE,
)
LOG = ROOT / "examples" / "live-recover-log.json"
TRANSCRIPT = ROOT / "examples" / "LAST_RECOVER_TRANSCRIPT.md"
INVOICE_PY = ROOT / "examples" / "live_fixture" / "invoice.py"
CID = "live-recover"

SEED_PROMPTS = [
    (
        "Fix examples/live_fixture/invoice.py so an exempt customer with a "
        "$100 subtotal has $0 tax and a $100 total. "
        "The check is: python3 -c \"import sys; sys.path.insert(0,'examples/live_fixture'); "
        "from invoice import total; assert total(100, exempt=True)==100\""
    ),
    "A reseller certificate exempts only the home state.",
    "A marketplace order is never exempt.",
]

BROKEN_INVOICE = """\
def total(subtotal, exempt=False):
    tax_rate = 0.08
    return subtotal + subtotal * tax_rate
"""


def fail(message: str, code: int = 1) -> int:
    print("FAIL: %s" % message, file=sys.stderr)
    return code


def maybe_reexec_venv() -> None:
    if sys.version_info >= (3, 10):
        return
    venv_py = ROOT / ".venv" / "bin" / "python"
    if not venv_py.is_file():
        return
    os.execv(str(venv_py), [str(venv_py), str(Path(__file__).resolve()), *sys.argv[1:]])


def load_api_key_from_zshrc() -> str | None:
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


def assistant_text(run) -> str:
    if hasattr(run, "text"):
        try:
            text = run.text()
            if isinstance(text, str) and text.strip():
                return text.strip()
        except Exception:
            pass
    wait = getattr(run, "wait", None)
    if callable(wait):
        result = wait()
        return str(getattr(result, "result", "") or getattr(result, "text", "") or "").strip()
    return str(getattr(run, "result", "") or "").strip()


def print_lane(lane: dict) -> None:
    print("")
    print("── %s ──" % lane.get("title"))
    print("WHO:      %s" % lane.get("who"))
    print("CHAT:     %s" % (lane.get("chat") or "")[:1200])
    print("PRODUCT:  %s" % lane.get("product"))
    if lane.get("why"):
        print("WHY:      %s" % lane.get("why"))
    if lane.get("unit"):
        print("UNIT:     %s" % lane.get("unit"))


def write_transcript(shown: str, reply: str, followup: str | None) -> None:
    body = [
        "# Last live recover run",
        "",
        "Source: `examples/live-recover-log.json` (Composer 2.5, Fast off).",
        "Seeded user prompts had no `Current goal:` and no leading `/goal`.",
        "Recover used production `CursorModelBootstrap`.",
        "",
        "## Recovered goal show",
        "",
        "```",
        shown.rstrip(),
        "```",
        "",
        "## Agent turn (model)",
        "",
        "```",
        (reply or "").rstrip(),
        "```",
        "",
        "Follow-up: %s" % (followup or "Silence"),
        "",
    ]
    TRANSCRIPT.write_text("\n".join(body), encoding="utf-8")


def main() -> int:
    maybe_reexec_venv()
    # Live bootstrap must call the model even when pytest shells this out.
    os.environ.pop("PYTEST_CURRENT_TEST", None)

    if sys.version_info < (3, 10):
        return fail("need Python >= 3.10", 2)
    try:
        from cursor_sdk import Agent, LocalAgentOptions
    except ImportError:
        return fail("cursor-sdk is not installed", 2)
    if not ensure_api_key():
        return fail("CURSOR_API_KEY is missing", 2)

    INVOICE_PY.parent.mkdir(parents=True, exist_ok=True)
    INVOICE_PY.write_text(BROKEN_INVOICE, encoding="utf-8")

    cycle = ChatCycle(CID)
    cycle.prompts = list(SEED_PROMPTS)
    assert cycle.show() == "No goal."

    print("")
    print("Recovering living goal from seeded prompts (real CursorModelBootstrap)…")
    cycle.observe_user("Recover goal")
    shown = cycle.show()
    print_lane(
        {
            "title": "1 Recover goal (user)",
            "who": "user",
            "chat": "Recover goal",
            "product": shown,
            "why": "observe_user → recover_from_prompts → CursorModelBootstrap",
            "unit": shown,
        }
    )

    errors: list[str] = []
    low = shown.lower()
    if shown == "No goal.":
        errors.append("recover left No goal.")
    if "exempt" not in low and "invoice" not in low:
        errors.append("recovered goal missing invoice/exempt sense: %s" % shown)
    if "home" not in low and "reseller" not in low:
        errors.append("recovered goal missing home-state / reseller detail: %s" % shown)
    if "marketplace" not in low:
        errors.append("recovered goal missing marketplace detail: %s" % shown)

    reply = ""
    followup = None
    explain: dict = {}
    check_exit = None

    try:
        with Agent.create(
            model=model_selection(),
            api_key=os.environ["CURSOR_API_KEY"].strip(),
            local=LocalAgentOptions(cwd=str(ROOT)),
        ) as agent:
            turn = (
                "The living goal is already recovered. Stay on it.\n"
                "Fix examples/live_fixture/invoice.py so total(100, exempt=True)==100, "
                "then run that check.\n"
                "Goal show:\n%s\n" % shown
            )
            run = agent.send(turn)
            reply = assistant_text(run)
            check = subprocess.run(
                "python3 -c \"import sys; sys.path.insert(0,'examples/live_fixture'); "
                "from invoice import total; assert total(100, exempt=True)==100\"",
                shell=True,
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                check=False,
            )
            check_exit = check.returncode
            cycle.record_check(check_exit, (check.stdout or check.stderr or "").strip())
            explain = cycle.explain_assistant(reply)
            followup = cycle.followup(reply)
            print_lane(
                {
                    "title": "2 Build on recovered goal (model)",
                    "who": "model",
                    "chat": reply,
                    "product": followup or "Silence",
                    "why": explain.get("reason"),
                    "unit": cycle.show(),
                }
            )
            if check_exit == 0 and followup:
                errors.append("check passed but followup spoke: %r" % followup)
            if check_exit not in (0, None) and (
                not followup or "check is still open" not in followup.lower()
            ):
                errors.append("red check did not keep the loop open: %r" % followup)
            if not reply.strip():
                errors.append("agent reply empty")
    except Exception as exc:
        errors.append("agent error: %s" % exc)

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": "%s fast=%s" % (MODEL_ID, MODEL_FAST),
        "seed_prompts": SEED_PROMPTS,
        "goal_show": cycle.show(),
        "agent_reply": reply,
        "followup": followup,
        "check_exit": check_exit,
        "explain": explain,
        "events": list(cycle.events),
        "errors": errors,
    }
    LOG.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_transcript(cycle.show(), reply, followup)

    if errors:
        print("FAIL live recover: %s" % "; ".join(errors), file=sys.stderr)
        return 1
    print("PASS live recover (%s fast=%s)" % (MODEL_ID, MODEL_FAST))
    print("Wrote %s" % LOG)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
