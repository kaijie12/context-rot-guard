from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from context_rot_guard import ContextRotGuard, GoalSpec

ROOT = Path(__file__).resolve().parents[1]


def test_session_roundtrip_and_revise(tmp_path: Path) -> None:
    path = tmp_path / "session.json"
    spec = GoalSpec(goal="Original mission", constraints=["do not push"], done_means="pytest exits 0")
    guard = ContextRotGuard(spec, session_path=path, compact_every=100, mention_gap=100)
    guard.add_turn("user", "hello")
    guard.record_check(1, "nope")
    loaded = ContextRotGuard.load(path)
    assert loaded.spec.goal == "Original mission"
    assert loaded.turn_count == 1
    assert loaded.checks[0].exit_code == 1
    assert loaded.intent_ring[0].content == "hello"

    loaded.revise(goal="Replacement mission")
    assert loaded.checks == []
    assert loaded.digest is None
    assert loaded.intent_ring == []
    assert loaded.turns[0].content == "hello"
    again = ContextRotGuard.load(path)
    assert again.spec.goal == "Replacement mission"
    assert again.checks == []


def test_cli_blocks_done_until_check_is_green(tmp_path: Path) -> None:
    session = tmp_path / "session.json"
    base = [
        sys.executable,
        "-m",
        "context_rot_guard",
        "--session",
        str(session),
    ]
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
            "--constraint",
            "do not push",
            "--check-cmd",
            "pytest -q",
            "--fail-streak",
            "3",
            "--mention-gap",
            "30",
        ]
    )
    assert init.returncode == 0, init.stderr
    assert run(["turn", "assistant", "Working on the export."]).returncode == 0
    for _ in range(3):
        checked = run(["check", "--exit-code", "1", "--log", "FAILED test_export"])
        assert checked.returncode == 0, checked.stderr
    status = json.loads(run(["status"]).stdout)
    assert status["drift"] is True
    assert "verify_stall" in status["reasons"]

    blocked = run(["done"])
    assert blocked.returncode == 2
    assert json.loads(blocked.stdout)["status"] == "blocked"

    messages = json.loads(run(["messages", "--json"]).stdout)
    assert any(item["meta"]["kind"] == "anchor" and "Ship the export" in item["content"] for item in messages)
    assert any(item["meta"]["kind"] == "drift" for item in messages)

    assert run(["check", "--exit-code", "0", "--log", "passed"]).returncode == 0
    # The assistant text still overlaps the goal, so mention-gap stays quiet.
    allowed = run(["done"])
    assert allowed.returncode == 0, allowed.stdout + allowed.stderr
    assert json.loads(allowed.stdout)["status"] == "done"
