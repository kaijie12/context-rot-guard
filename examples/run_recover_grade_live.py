#!/usr/bin/env python3
"""Grade the recovered summary for the frozen this-chat fixture.

Prints three blocks, in order: product goal show, rubric, external grade.
Writes the same blocks plus the dialogue, grader prompt, and raw model text to
examples/live-recover-grade.json and examples/LAST_RECOVER_GRADE.md after each
stage, so a timeout still leaves a log.

Exit 0 only when the external grader returns pass true.
Requires Python >= 3.10, cursor-sdk, CURSOR_API_KEY (env or ~/.zshrc).
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_guard.cycle import ChatCycle  # noqa: E402
from context_guard.judge import RECOVER_RUBRIC, CursorModelGrader  # noqa: E402

FIXTURE = ROOT / "examples" / "fixtures" / "recover_this_chat_users.json"
LOG = ROOT / "examples" / "live-recover-grade.json"
TRANSCRIPT = ROOT / "examples" / "LAST_RECOVER_GRADE.md"
CID = "recover-grade-this-chat"
_ZSHRC_KEY = re.compile(
    r"""^\s*(?:export\s+)?CURSOR_API_KEY\s*=\s*(['\"]?)([^'\"\n]+)\1\s*$""",
    re.MULTILINE,
)


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


def write_logs(record: dict) -> None:
    LOG.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Recover grade",
        "",
        "Written %s" % record.get("written_at", ""),
        "",
        "## Product goal show",
        "",
        record.get("product_goal_show") or "(not yet)",
        "",
        "## Rubric",
        "",
        record.get("rubric") or "",
        "",
        "## External grade",
        "",
        "```json",
        json.dumps(record.get("grade") or {}, indent=2, ensure_ascii=False),
        "```",
        "",
        "## Grader raw",
        "",
        record.get("grader_raw") or "(none)",
        "",
        "## Grader prompt",
        "",
        record.get("grader_prompt") or "(none)",
        "",
        "## Dialogue",
        "",
    ]
    for index, line in enumerate(record.get("dialogue") or [], start=1):
        lines.append("### %s" % index)
        lines.append("")
        lines.append(line)
        lines.append("")
    TRANSCRIPT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    maybe_reexec_venv()
    os.environ.pop("PYTEST_CURRENT_TEST", None)
    record: dict = {
        "conversation_id": "e0957c65-48ed-4aff-918c-70de1f6b2124",
        "fixture": str(FIXTURE.relative_to(ROOT)),
        "written_at": datetime.now(timezone.utc).isoformat(),
        "dialogue": [],
        "product_goal_show": "",
        "rubric": RECOVER_RUBRIC,
        "grader_model": CursorModelGrader.model_id,
        "grader_fast": False,
        "grader_prompt": "",
        "grader_raw": "",
        "grade": None,
        "exit": 1,
    }
    if not FIXTURE.is_file():
        record["grade"] = {"pass": None, "fails": [], "notes": "missing fixture", "available": False}
        write_logs(record)
        print("## Product goal show\n\nNo goal.\n\n## Rubric\n\n%s\n## External grade\n\nmissing fixture" % RECOVER_RUBRIC)
        return 1
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    dialogue = [str(line) for line in (payload.get("lines") or []) if str(line).strip()]
    record["dialogue"] = dialogue
    write_logs(record)

    if not ensure_api_key():
        record["grade"] = {"pass": None, "fails": [], "notes": "no CURSOR_API_KEY", "available": False}
        record["product_goal_show"] = "No goal."
        write_logs(record)
        print("## Product goal show\n\nNo goal.\n")
        print("## Rubric\n\n%s" % RECOVER_RUBRIC)
        print("## External grade\n\n%s" % json.dumps(record["grade"]))
        return 1

    cycle = ChatCycle(CID)
    cycle.recover_from_prompts(dialogue)
    shown = cycle.show()
    record["product_goal_show"] = shown
    record["written_at"] = datetime.now(timezone.utc).isoformat()
    write_logs(record)

    print("## Product goal show\n")
    print(shown)
    print("\n## Rubric\n")
    print(RECOVER_RUBRIC)

    grade = CursorModelGrader().grade(dialogue=dialogue, goal_show=shown, rubric=RECOVER_RUBRIC)
    record["grader_prompt"] = grade.get("prompt") or ""
    record["grader_raw"] = grade.get("raw") or ""
    record["grade"] = {
        "pass": grade.get("pass"),
        "fails": list(grade.get("fails") or []),
        "notes": grade.get("notes") or "",
        "available": grade.get("available"),
        "model": grade.get("model"),
        "fallback_from": grade.get("fallback_from"),
        "fallback_reason": grade.get("fallback_reason"),
    }
    passed = grade.get("available") is True and grade.get("pass") is True
    record["exit"] = 0 if passed else 1
    record["written_at"] = datetime.now(timezone.utc).isoformat()
    write_logs(record)

    print("## External grade\n")
    print(json.dumps(record["grade"], indent=2))
    return int(record["exit"])


if __name__ == "__main__":
    # A timed-out grader thread must not keep this process alive. Stop waits on the process.
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
