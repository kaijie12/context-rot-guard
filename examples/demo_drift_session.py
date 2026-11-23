"""Fake a 40-turn session that leaves the mission, then show compact + anchor + drift."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_rot_guard import ContextRotGuard, GoalSpec  # noqa: E402


def main() -> int:
    spec = GoalSpec(
        goal=(
            "Add max-length validation so usernames longer than 20 characters "
            "are rejected in src/username.js"
        ),
        constraints=["Do not edit tests", "Do not push"],
        done_means="pytest -q exits 0",
        check_cmd="pytest -q",
        allow_paths=["src/username.js"],
    )
    guard = ContextRotGuard(
        spec,
        compact_every=10,
        anchor_every=5,
        fail_streak=3,
        token_ceiling=100000,
        keep_recent=6,
        mention_gap=8,
    )

    on_goal = [
        ("user", "Please add max-length validation in src/username.js."),
        ("assistant", "I will add validation so longer usernames are rejected."),
        ("tool", "read src/username.js\n" + ("function stub\n" * 80)),
        ("assistant", "Implemented the length check. Still need a green pytest run."),
        ("user", "Keep going until pytest exits 0. Do not edit tests."),
        ("assistant", "Running pytest next."),
        ("tool", "pytest -q\nFAILED tests/username.test.js\n" + ("E assert\n" * 40)),
        ("assistant", "The check failed. I will stay on username validation."),
    ]
    for role, content in on_goal:
        guard.add_turn(role, content)

    before = guard.process()
    before_count = len(before)

    side = [
        "Looking at the marketing homepage instead.",
        "Reworking the hero spacing on the marketing homepage.",
        "Edited docs/marketing.css to enlarge the hero.",
        "Edited site/home.css for the footer.",
        "Edited site/nav.css for the top bar.",
        "The homepage is done",
    ]
    # Pad to 40 total turns (8 already recorded) with noisy tool output, then the side quest.
    while guard.turn_count < 34:
        guard.add_turn(
            "tool",
            "homepage build log %d\n" % guard.turn_count + ("warning: unused style\n" * 30),
        )
    for content in side:
        guard.add_turn("assistant", content)

    for _ in range(3):
        guard.record_check(1, "FAILED tests/username.test.js :: expected false, got true")

    after = guard.process()
    blob = "\n".join(message["content"] for message in after)
    status = guard.status()
    done = guard.attempt_done()
    kinds = [message["meta"]["kind"] for message in after]

    print("before_messages=%d raw_turns_at_before=8" % before_count)
    print(
        "after_messages=%d raw_turns=%d kept_raw_turns=%d"
        % (len(after), guard.turn_count, status["turns_retained"])
    )
    print("goal_verbatim=%s" % str(spec.goal in blob).lower())
    print("anchor=%s" % str("anchor" in kinds).lower())
    print("digest=%s" % str("## SessionDigest" in blob).lower())
    print(
        "DRIFT drift=%s fail_streak=%d reasons=%s"
        % (str(status["drift"]).lower(), status["fail_streak"], ",".join(status["reasons"]))
    )
    print("done_status=%s reason=%s" % (done["status"], done.get("reason", "")))

    if spec.goal not in blob:
        print("demo failed: goal text missing after compaction", file=sys.stderr)
        return 1
    if "anchor" not in kinds or "## SessionDigest" not in blob:
        print("demo failed: expected digest and anchor", file=sys.stderr)
        return 1
    if not status["drift"] or status["fail_streak"] < 3:
        print("demo failed: expected drift from the fail streak", file=sys.stderr)
        return 1
    if done["status"] != "blocked":
        print("demo failed: synthetic done should be blocked", file=sys.stderr)
        return 1
    if len(after) >= before_count + 30:
        print("demo failed: compaction did not shrink the window", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
