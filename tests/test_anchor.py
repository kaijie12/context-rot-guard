from __future__ import annotations

from context_guard import ContextRotGuard, GoalSpec


def _guard(**kwargs: object) -> ContextRotGuard:
    spec = GoalSpec(
        goal="Keep the billing export idempotent",
        constraints=["do not push"],
        done_means="pytest -q exits 0",
        check_cmd="pytest -q",
    )
    defaults = dict(compact_every=100, token_ceiling=10**9, mention_gap=100, fail_streak=99)
    defaults.update(kwargs)
    return ContextRotGuard(spec, **defaults)  # type: ignore[arg-type]


def test_pin_always_contains_goal_and_done_means() -> None:
    guard = _guard(anchor_every=5)
    guard.add_turn("user", "start")
    messages = guard.process()
    pin = next(message for message in messages if message["meta"]["kind"] == "pin")
    assert guard.spec.goal in pin["content"]
    assert guard.spec.done_means in pin["content"]
    assert all(message["meta"]["kind"] != "anchor" for message in messages)


def test_anchor_every_n_turns() -> None:
    guard = _guard(anchor_every=5)
    for index in range(4):
        guard.add_turn("user", "step %d" % index)
    assert all(message["meta"]["kind"] != "anchor" for message in guard.process())
    guard.add_turn("user", "step 4")
    messages = guard.process()
    anchors = [message for message in messages if message["meta"]["kind"] == "anchor"]
    assert len(anchors) == 1
    assert guard.spec.goal in anchors[0]["content"]
    assert "pytest -q exits 0" in anchors[0]["content"]


def test_anchor_forced_before_completion_and_on_drift() -> None:
    guard = _guard(anchor_every=5)
    guard.add_turn("user", "only one")
    forced = guard.process(before_completion=True)
    assert any(message["meta"]["kind"] == "anchor" for message in forced)

    stalled = _guard(anchor_every=50, fail_streak=3, mention_gap=100)
    stalled.add_turn("assistant", "still working")
    for _ in range(3):
        stalled.record_check(1, "FAILED")
    messages = stalled.process()
    assert any(message["meta"]["kind"] == "anchor" for message in messages)
    assert any(message["meta"]["kind"] == "drift" for message in messages)
