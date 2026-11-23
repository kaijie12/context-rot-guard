from __future__ import annotations

from context_rot_guard import ContextRotGuard, GoalSpec, SessionDigest


def _spec() -> GoalSpec:
    return GoalSpec(
        goal="UNIQUE_GOAL_PHRASE_keep_verbatim",
        constraints=["do not push"],
        done_means="pytest -q exits 0",
        check_cmd="pytest -q",
    )


def test_goal_survives_compaction_of_50_turns() -> None:
    spec = _spec()
    guard = ContextRotGuard(
        spec,
        compact_every=10,
        keep_recent=5,
        token_ceiling=10**9,
        mention_gap=100,
        fail_streak=99,
    )
    for index in range(50):
        guard.add_turn("tool", "NOISE_%d_%s" % (index, "x" * 40))

    messages = guard.process()
    blob = "\n".join(message["content"] for message in messages)
    assert spec.goal in blob
    assert guard.digest is not None
    assert guard.digest.goal == spec.goal
    assert "NOISE_0_" not in blob
    assert [message["meta"]["kind"] for message in messages].count("turn") == 5
    assert "## SessionDigest" in blob


def test_token_ceiling_compacts_before_turn_limit() -> None:
    guard = ContextRotGuard(
        _spec(),
        compact_every=100,
        token_ceiling=50,
        keep_recent=3,
        mention_gap=100,
        fail_streak=99,
    )
    for _ in range(9):
        guard.add_turn("tool", "y" * 400)
    guard.process()
    assert guard.digest is not None
    assert len(guard.turns) == 3


def test_tool_turns_are_truncated_on_ingest() -> None:
    guard = ContextRotGuard(_spec(), compact_every=100, mention_gap=100, fail_streak=99)
    guard.add_turn("tool", "HEAD" + ("z" * 5000) + "TAILMARK")
    stored = guard.turns[0].content
    assert "HEAD" in stored
    assert "TAILMARK" in stored
    assert "truncated" in stored
    assert len(stored) < 5000


def test_digest_keeps_done_open_and_verify_snippet() -> None:
    spec = _spec()
    guard = ContextRotGuard(
        spec,
        compact_every=4,
        keep_recent=1,
        token_ceiling=10**9,
        mention_gap=100,
        fail_streak=99,
    )
    guard.add_turn("assistant", "Implemented the parser.")
    guard.add_turn("assistant", "TODO: cover the empty input")
    guard.add_turn("tool", "FAIL " + ("e" * 800))
    guard.record_check(1, "FAILED test_parser — assertion")
    guard.add_turn("user", "continue")
    guard.process()
    assert guard.digest is not None
    assert any("Implemented the parser" in item for item in guard.digest.done_so_far)
    assert any("TODO: cover the empty input" in item for item in guard.digest.open_items)
    assert guard.digest.last_verify is not None
    assert guard.digest.last_verify["exit_code"] == 1
    assert "assertion" in str(guard.digest.last_verify["output_tail"])


def test_summarizer_cannot_replace_the_goal() -> None:
    spec = _spec()

    def rewrite(digest: SessionDigest) -> SessionDigest:
        digest.goal = "rewritten by the model"
        digest.done_so_far = ["summarizer: folded"]
        return digest

    guard = ContextRotGuard(
        spec,
        summarizer=rewrite,
        compact_every=4,
        keep_recent=2,
        token_ceiling=10**9,
        mention_gap=100,
        fail_streak=99,
    )
    for index in range(4):
        guard.add_turn("user", "note %d" % index)
    guard.process()
    assert guard.digest is not None
    assert guard.digest.goal == spec.goal
    assert guard.digest.done_so_far == ["summarizer: folded"]
