from __future__ import annotations

import pytest

from context_rot_guard import ContextRotGuard, EmbeddingDriftDetector, GoalSpec


def _guard(goal: str = "Ship username validation", **kwargs: object) -> ContextRotGuard:
    spec = GoalSpec(
        goal=goal,
        constraints=["Do not edit tests"],
        done_means="pytest -q exits 0",
        check_cmd="pytest -q",
    )
    defaults = dict(compact_every=100, token_ceiling=10**9, mention_gap=100, fail_streak=3)
    defaults.update(kwargs)
    return ContextRotGuard(spec, **defaults)  # type: ignore[arg-type]


def test_fail_streak_sets_drift_and_resets_on_green() -> None:
    guard = _guard()
    guard.add_turn("assistant", "Working on username validation.")
    first = guard.record_check(1, "FAILED")
    second = guard.record_check(1, "FAILED")
    assert first.drift is False
    assert second.fail_streak == 2
    third = guard.record_check(1, "FAILED")
    assert third.drift is True
    assert "verify_stall" in third.reasons
    assert third.block_done is True
    status = guard.status()
    assert status["drift"] is True
    assert status["fail_streak"] == 3

    cleared = guard.record_check(0, "passed")
    assert cleared.fail_streak == 0
    assert cleared.drift is False
    assert guard.attempt_done()["status"] == "done"


def test_done_blocked_when_verify_is_red_without_full_streak() -> None:
    guard = _guard(fail_streak=9)
    guard.add_turn("assistant", "Working on username validation.")
    guard.record_check(1, "FAILED one assertion")
    result = guard.attempt_done()
    assert result["status"] == "blocked"
    assert result["reason"] == "verify_red"


def test_done_blocked_with_no_check() -> None:
    guard = _guard()
    guard.add_turn("assistant", "Working on username validation.")
    assert guard.attempt_done() == {"status": "blocked", "reason": "no_verify", "drift": False}


def test_goal_mention_gap() -> None:
    guard = _guard(mention_gap=4, fail_streak=9)
    for _ in range(4):
        guard.add_turn("assistant", "Adjust the homepage layout and spacing")
    report = guard.evaluate()
    assert report.reasons == ["goal_mention_gap"]
    assert report.drift is True


def test_side_quest_ratio() -> None:
    guard = _guard(goal="Update src/username.js", mention_gap=4, fail_streak=9)
    guard.add_turn(
        "assistant",
        "Edited docs/marketing.css and site/home.css and site/nav.css",
    )
    report = guard.evaluate()
    assert "side_quest" in report.reasons
    assert report.signals["side_quest_ratio"] == 1.0


def test_completion_without_green() -> None:
    guard = _guard(fail_streak=9, mention_gap=100)
    guard.add_turn("assistant", "I am done")
    report = guard.record_check(1, "FAILED")
    assert "completion_without_green" in report.reasons
    assert report.block_done is True
    assert guard.attempt_done()["status"] == "blocked"


def test_embedding_detector_is_a_stub() -> None:
    with pytest.raises(NotImplementedError):
        EmbeddingDriftDetector().score("goal text", "recent intent")
