#!/usr/bin/env python3
"""Replay the real add.py build and the model's homepage reply.

Prints two lanes: what was said, and what context-guard decided.
Writes examples/live-build-log.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_guard.cycle import ChatCycle  # noqa: E402

UNIT = (
    "add a function add(a, b) in examples/live_fixture/add.py "
    "that returns the sum of two numbers."
)
BUILD_REPLY = "The check passed. add(a, b) returns the sum of two numbers."
SIDETRACK_REPLY = (
    "The homepage is a short marketing page for a note-taking app. "
    "It opens with a headline about keeping every note where you left it, "
    "lists three features (quick capture and search, notebooks, and sync across devices), "
    "and ends with a free signup line."
)


def main() -> int:
    add_py = (ROOT / "examples" / "live_fixture" / "add.py").read_text(encoding="utf-8")
    homepage = (ROOT / "examples" / "live_fixture" / "HOMEPAGE.md").read_text(encoding="utf-8")
    if "return a + b" not in add_py or "Sign up free" not in homepage:
        print("missing live fixture files", file=sys.stderr)
        return 1

    cycle = ChatCycle("live-build")
    lanes = []

    def lane(chat: str, decision: str) -> None:
        lanes.append({"chat": chat, "product": decision})
        print("CHAT:    %s" % chat)
        print("PRODUCT: %s" % decision)
        print("---")

    cycle.observe_user("Current unit: %s" % UNIT)
    lane("You: Current unit: %s" % UNIT, "Open unit. Pin armed. Chat stays quiet.")

    cycle.observe_tool("Write", {"path": "examples/live_fixture/add.py", "content": add_py})
    cycle.record_check(0, "passed")
    note = cycle.followup(BUILD_REPLY)
    lane(
        "Agent: wrote add.py, check passed. %s" % BUILD_REPLY,
        "Quiet stop." if note is None else note,
    )

    note = cycle.followup(SIDETRACK_REPLY)
    lane("Agent: %s" % SIDETRACK_REPLY, note or "No redirect (product missed the sidetrack).")

    out = ROOT / "examples" / "live-build-log.json"
    payload = {
        "unit_after": None if cycle.unit is None else cycle.unit["goal"],
        "redirect": note,
        "lanes": lanes,
        "add_py": "examples/live_fixture/add.py",
        "homepage": "examples/live_fixture/HOMEPAGE.md",
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("log=%s" % out)
    if not note or "no drift" in note.lower() or "homepage" in (cycle.unit or {}).get("goal", "").lower():
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
