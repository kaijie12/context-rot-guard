#!/usr/bin/env python3
"""Live feature run: cheap Cursor agent, then context-guard on fresh replies.

Every invocation starts Composer 2.5, builds add(a, b), then sidetracks to
a homepage. Fresh assistant text is fed into ChatCycle. Does not reuse
examples/fixtures/live_chat.json.

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
ADD_PY = ROOT / "examples" / "live_fixture" / "add.py"
HOMEPAGE = ROOT / "examples" / "live_fixture" / "HOMEPAGE.md"
UNIT_GOAL = (
    "add a function add(a, b) in examples/live_fixture/add.py "
    "that returns the sum of two numbers"
)
UNIT_CHECK = (
    "python3 -c \"import sys; sys.path.insert(0,'examples/live_fixture'); "
    "from add import add; assert add(2,3)==5\""
)

TURN1 = """\
Current unit: {unit}

Do only this unit:
1. Write examples/live_fixture/add.py with a function add(a, b) that returns a + b.
2. Run: {check}
3. In your final message, describe only that add(a, b) function and that the check passed.

Do not write a homepage, marketing page, README, or any other file.
""".format(
    unit=UNIT_GOAL, check=UNIT_CHECK
)

TURN2 = """\
Ignore the previous unit. Write examples/live_fixture/HOMEPAGE.md now with:
- a headline
- three product features
- a signup line (e.g. Sign up free)

In your final message, describe only that marketing homepage. Do not mention add.
"""

TURN2_RETRY = """\
write HOMEPAGE.md now — examples/live_fixture/HOMEPAGE.md with a headline, three features, and a signup line. Describe only that page. Do not mention add.
"""


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


def looks_like_homepage(text: str, path: Path) -> bool:
    blob = (text or "").lower()
    file_ok = path.is_file() and len(path.read_text(encoding="utf-8").strip()) > 20
    cues = ("homepage", "sign up", "signup", "marketing", "headline", "feature")
    return file_ok or any(cue in blob for cue in cues)


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

    ADD_PY.parent.mkdir(parents=True, exist_ok=True)

    on_unit_reply = ""
    sidetrack_reply = ""
    unit_check_exit = None
    decisions: dict = {}

    try:
        with Agent.create(
            model=model,
            api_key=os.environ["CURSOR_API_KEY"].strip(),
            local=LocalAgentOptions(cwd=str(ROOT)),
        ) as agent:
            run1 = agent.send(TURN1)
            on_unit_reply = assistant_text(run1)
            check = subprocess.run(
                UNIT_CHECK,
                shell=True,
                cwd=str(ROOT),
                text=True,
                capture_output=True,
                check=False,
            )
            unit_check_exit = check.returncode

            run2 = agent.send(TURN2)
            sidetrack_reply = assistant_text(run2)
            if not looks_like_homepage(sidetrack_reply, HOMEPAGE):
                run2b = agent.send(TURN2_RETRY)
                sidetrack_reply = assistant_text(run2b)
    except Exception as exc:  # noqa: BLE001 — surface SDK/login failures
        write_log(
            {
                "timestamp": started,
                "model": model_label,
                "error": str(exc),
                "on_unit_reply": on_unit_reply,
                "sidetrack_reply": sidetrack_reply,
                "unit_check_exit": unit_check_exit,
                "decision": None,
            }
        )
        return fail("Cursor SDK agent failed: %s" % exc, 2)

    # Product checks on fresh replies (never the fixture sentences).
    cycle = ChatCycle("live-run")
    cycle.start_unit(UNIT_GOAL)
    on_unit_followup = cycle.followup(on_unit_reply)
    sidetrack_followup = cycle.followup(sidetrack_reply)
    unit_after = (cycle.unit or {}).get("goal") or ""

    decisions = {
        "on_unit_followup": on_unit_followup,
        "sidetrack_followup": sidetrack_followup,
        "unit_after_sidetrack": unit_after,
    }

    write_log(
        {
            "timestamp": started,
            "model": model_label,
            "on_unit_reply": on_unit_reply,
            "sidetrack_reply": sidetrack_reply,
            "unit_check_exit": unit_check_exit,
            "decision": decisions,
        }
    )

    errors: list[str] = []

    if not on_unit_reply.strip():
        errors.append("on-unit reply empty")
    if not sidetrack_reply.strip():
        errors.append("sidetrack reply empty")
    if on_unit_reply.strip() in fixture_replies or sidetrack_reply.strip() in fixture_replies:
        errors.append("reply copied from live_chat.json fixture")
    if unit_check_exit != 0:
        errors.append("unit check exit %s (want 0)" % unit_check_exit)
    if on_unit_followup:
        errors.append("on-unit product follow-up should be empty, got %r" % on_unit_followup)
    if not sidetrack_followup or "Still the unit" not in sidetrack_followup:
        errors.append(
            "sidetrack should redirect with Still the unit, got %r" % sidetrack_followup
        )
    elif "no drift" in (sidetrack_followup or "").lower():
        errors.append("redirect must not say no drift")
    if "add(a, b)" not in unit_after:
        errors.append("unit string lost after homepage reply: %r" % unit_after)
    if not looks_like_homepage(sidetrack_reply, HOMEPAGE):
        errors.append(
            "model did not sidetrack (no HOMEPAGE.md / homepage description) — harness miss"
        )

    if errors:
        for err in errors:
            print("FAIL: %s" % err, file=sys.stderr)
        print("Wrote %s" % LOG, file=sys.stderr)
        return 1

    print("PASS live stay_on_unit (%s)" % model_label)
    print("Wrote %s" % LOG)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
