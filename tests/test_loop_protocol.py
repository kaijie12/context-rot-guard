from __future__ import annotations

import json
from pathlib import Path

from context_rot_guard import AcceptanceContract, ContextRotGuard, GoalSpec, GuardConfig
from context_rot_guard.loop import contract_for_check


def _guard(**kwargs: object) -> ContextRotGuard:
    spec = GoalSpec(
        goal="Ship username validation",
        constraints=["Do not edit tests"],
        done_means="pytest -q exits 0",
        check_cmd="pytest -q",
        allow_paths=["src/username.py"],
        acceptance=contract_for_check("pytest -q", unit_id="username-validation"),
    )
    config = GuardConfig(compact_every=100, token_ceiling=10**9, mention_gap=100, fail_streak_limit=9)
    for key, value in kwargs.items():
        setattr(config, key, value)
    config.__post_init__()
    return ContextRotGuard(spec, config=config)


def test_red_check_returns_one_unit_and_keeps_legacy_done_keys() -> None:
    guard = _guard()
    guard.add_turn("assistant", "Working on username validation.")
    guard.record_check(1, "FAILED test_length")
    packet = guard.correction_packet()
    assert packet is not None
    assert packet.unit_id == "username-validation"
    assert packet.failed_rule == "verify_red"
    assert packet.next_route == "correct"
    assert packet.allowed_scope == ["src/username.py"]
    assert packet.evidence == "FAILED test_length"
    legacy = guard.attempt_done()
    assert legacy == {
        "status": "blocked",
        "reason": "verify_red",
        "exit_code": 1,
        "drift": False,
    }
    messages = guard.process()
    correction = next(message for message in messages if message["meta"]["kind"] == "correction")
    assert "username-validation" in correction["content"]
    assert "Fix this unit only" in correction["content"]


def test_no_check_has_no_correction_and_legacy_no_verify() -> None:
    guard = _guard()
    assert guard.correction_packet() is None
    assert guard.attempt_done() == {"status": "blocked", "reason": "no_verify", "drift": False}
    assert all(message["meta"]["kind"] != "correction" for message in guard.process())


def test_attempt_cap_escalates_before_another_correction() -> None:
    guard = _guard(max_check_attempts=2)
    guard.record_check(1, "FAILED one")
    assert guard.attempt_done()["reason"] == "verify_red"
    guard.record_check(1, "FAILED two")
    result = guard.attempt_done()
    assert result["reason"] == "attempt_cap"
    assert result["next_route"] == "escalate"
    assert result["attempt"] == 2
    packet = guard.correction_packet()
    assert packet is not None
    assert packet.next_route == "escalate"
    text = next(
        message["content"]
        for message in guard.process()
        if message["meta"]["kind"] == "correction"
    )
    assert "Stop correcting" in text


def test_identical_red_output_is_no_progress() -> None:
    guard = _guard(no_progress_window=2)
    guard.record_check(1, "FAILED same")
    assert guard.attempt_done()["reason"] == "verify_red"
    guard.record_check(1, "FAILED same")
    assert guard.attempt_done()["reason"] == "no_progress"
    assert guard.attempt_done()["next_route"] == "escalate"


def test_different_red_output_is_still_a_correction() -> None:
    guard = _guard(no_progress_window=2)
    guard.record_check(1, "FAILED one")
    guard.record_check(1, "FAILED two")
    assert guard.attempt_done()["reason"] == "verify_red"


def test_attempt_cap_wins_over_no_progress() -> None:
    guard = _guard(max_check_attempts=2, no_progress_window=2)
    guard.record_check(1, "FAILED same")
    guard.record_check(1, "FAILED same")
    assert guard.attempt_done()["reason"] == "attempt_cap"


def test_green_check_clears_the_packet() -> None:
    guard = _guard(max_check_attempts=3)
    guard.record_check(1, "FAILED")
    guard.record_check(0, "passed")
    assert guard.correction_packet() is None
    assert guard.attempt_done()["status"] == "done"
    assert guard.status()["next_route"] == "pass"


def test_custom_expected_exit_is_rejected() -> None:
    try:
        AcceptanceContract(check_cmd="pytest -q", expected_exit=2)
    except ValueError as exc:
        assert "expected_exit" in str(exc)
    else:
        raise AssertionError("expected_exit other than 0 must fail")


def test_session_without_new_fields_still_loads(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    payload = {
        "version": 1,
        "spec": {
            "goal": "Keep the old mission",
            "constraints": [],
            "done_means": "pytest exits 0",
            "check_cmd": None,
            "allow_paths": [],
        },
        "config": {
            "compact_every": 20,
            "anchor_every": 5,
            "fail_streak_limit": 3,
            "token_ceiling": 8000,
            "keep_recent": 8,
            "mention_gap": 12,
            "tool_char_limit": 1200,
            "side_quest_ratio": 0.6,
            "block_done_on_red": True,
            "intent_ring_limit": 24,
        },
        "turns": [],
        "intent_ring": [],
        "turn_count": 0,
        "digest": None,
        "checks": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    guard = ContextRotGuard.load(path)
    assert guard.spec.acceptance is None
    assert guard.config.max_check_attempts is None
    assert guard.attempt_done() == {"status": "blocked", "reason": "no_verify", "drift": False}
