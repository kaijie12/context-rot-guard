from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from context_guard import ContextRotGuard, GoalSpec
from context_guard.models import GuardConfig

ROOT = Path(__file__).resolve().parents[1]


def _guard(**kwargs: object) -> ContextRotGuard:
    spec = GoalSpec(
        goal="Ship username validation",
        constraints=["Do not edit tests"],
        done_means="pytest -q exits 0",
        check_cmd="pytest -q",
    )
    defaults = dict(compact_every=100, token_ceiling=10**9, mention_gap=100, fail_streak=3)
    defaults.update(kwargs)
    return ContextRotGuard(spec, **defaults)  # type: ignore[arg-type]


def test_events_cover_compact_drift_quality_and_blocked_done() -> None:
    guard = _guard(compact_every=4, keep_recent=2, mention_gap=100, fail_streak=3)
    for index in range(6):
        guard.add_turn("tool", "noise_%d_%s" % (index, "x" * 40))
    guard.process()
    actions = [event["action"] for event in guard.events]
    assert "compact" in actions

    for _ in range(3):
        guard.record_check(1, "FAILED")
    assert any(event["action"] == "drift" for event in guard.events)

    payload = guard.quality_check()
    assert payload["done_preview"]["status"] == "blocked"
    assert any(event["action"] == "quality_check" for event in guard.events)

    blocked = guard.attempt_done()
    assert blocked["status"] == "blocked"
    assert any(event["action"] == "blocked_done" for event in guard.events)


def test_events_survive_save_and_load(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    guard = _guard(session_path=path, fail_streak=2, mention_gap=100)
    guard.add_turn("assistant", "Working on username validation.")
    guard.record_check(1, "FAILED")
    guard.record_check(1, "FAILED")
    guard.quality_check()
    before = list(guard.events)
    assert before
    assert any(event["action"] == "drift" for event in before)

    loaded = ContextRotGuard.load(path)
    assert [event["action"] for event in loaded.events] == [event["action"] for event in before]
    assert loaded.events[0]["ts"] == before[0]["ts"]


def test_enable_compact_false_skips_digest() -> None:
    config = GuardConfig(
        compact_every=4,
        keep_recent=2,
        token_ceiling=10**9,
        mention_gap=100,
        fail_streak_limit=99,
        enable_compact=False,
    )
    guard = ContextRotGuard(
        GoalSpec(goal="UNIQUE_GOAL", constraints=[], done_means="pytest exits 0"),
        config=config,
    )
    for index in range(50):
        guard.add_turn("tool", "NOISE_%d_%s" % (index, "x" * 40))
    guard.process()
    assert guard.digest is None
    assert len(guard.turns) == 50
    assert all(event["action"] != "compact" for event in guard.events)


def test_cli_quality_check_exit_codes(tmp_path: Path) -> None:
    session = tmp_path / "session.json"
    base = [sys.executable, "-m", "context_guard", "--session", str(session)]
    env = dict(**{key: value for key, value in __import__("os").environ.items()})
    env["PYTHONPATH"] = str(ROOT / "src")

    def run(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            base + args,
            cwd=str(tmp_path),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    init = run(
        [
            "init",
            "--goal",
            "Ship the export",
            "--done-means",
            "pytest -q exits 0",
            "--check-cmd",
            "pytest -q",
            "--fail-streak",
            "3",
            "--mention-gap",
            "30",
            "--no-compact",
        ]
    )
    assert init.returncode == 0, init.stderr
    assert json.loads(init.stdout)["enable_compact"] is False

    assert run(["turn", "assistant", "Working on the export."]).returncode == 0
    red = run(["quality-check"])
    assert red.returncode == 2, red.stdout + red.stderr
    payload = json.loads(red.stdout)
    assert payload["done_preview"]["status"] == "blocked"
    assert payload["done_preview"]["reason"] == "no_verify"

    assert run(["check", "--exit-code", "0", "--log", "passed"]).returncode == 0
    green = run(["quality-check"])
    assert green.returncode == 0, green.stdout + green.stderr
    assert json.loads(green.stdout)["done_preview"]["status"] == "done"

    logged = run(["log", "--tail", "5"])
    assert logged.returncode == 0
    events = json.loads(logged.stdout)
    assert any(event["action"] == "quality_check" for event in events)
