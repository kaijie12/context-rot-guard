from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from context_guard import ContextRotGuard, GoalSpec
from context_guard.models import GuardConfig

ROOT = Path(__file__).resolve().parents[1]


def test_pulse_speaks_every_n_and_always_on_drift() -> None:
    guard = ContextRotGuard(
        GoalSpec(goal="Ship username validation", done_means="pytest exits 0"),
        config=GuardConfig(
            pulse_every=3,
            mention_gap=100,
            fail_streak_limit=9,
            enable_compact=False,
        ),
    )
    first = guard.pulse(snippet="Working on username validation")
    assert first["note"] == "no drift detected"
    assert first["should_speak"] is False
    assert guard.pulse()["should_speak"] is False
    third = guard.pulse()
    assert third["should_speak"] is True
    assert third["note"] == "no drift detected"

    recorded = guard.pulse(snippet="still on username validation", record_only=True)
    assert recorded["record_only"] is True
    assert recorded["should_speak"] is False
    assert recorded["pulse_count"] == 3

    drifted = ContextRotGuard(
        GoalSpec(goal="Ship username validation", done_means="pytest exits 0"),
        config=GuardConfig(
            pulse_every=99,
            mention_gap=3,
            fail_streak_limit=9,
            enable_compact=False,
        ),
    )
    for _ in range(3):
        drifted.add_turn("assistant", "homepage layout only")
    hit = drifted.pulse(snippet="more homepage spacing")
    assert hit["drift"] is True
    assert hit["should_speak"] is True
    assert hit["note"].startswith("drift detected")


def test_ensure_recreates_empty_session_file(tmp_path: Path) -> None:
    session = tmp_path / "empty.json"
    session.write_text("", encoding="utf-8")
    env = dict(**{key: value for key, value in __import__("os").environ.items()})
    env["PYTHONPATH"] = str(ROOT / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "context_guard",
            "--session",
            str(session),
            "pulse",
            "--ensure",
            "--bootstrap-only",
        ],
        cwd=str(tmp_path),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ready"
    assert json.loads(session.read_text(encoding="utf-8"))["spec"]["goal"]


def test_cli_pulse_ensure_and_hook_script(tmp_path: Path) -> None:
    session = tmp_path / "session.json"
    env = dict(**{key: value for key, value in __import__("os").environ.items()})
    env["PYTHONPATH"] = str(ROOT / "src")
    env["CONTEXT_ROT_SESSION"] = str(session)
    base = [sys.executable, "-m", "context_guard", "--session", str(session)]

    one = subprocess.run(
        base + ["pulse", "--ensure", "--pulse-every", "1", "--plain"],
        cwd=str(tmp_path),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert one.returncode == 0, one.stderr
    assert "no drift detected" in one.stdout

    two = subprocess.run(
        base + ["pulse"],
        cwd=str(tmp_path),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert two.returncode == 0, two.stderr
    payload = json.loads(two.stdout)
    assert payload["note"] == "no drift detected"
    assert payload["should_speak"] is True  # pulse_every=1 from ensure config

    hook = ROOT / ".cursor" / "hooks" / "rot-pulse.sh"
    hooked = subprocess.run(
        ["bash", str(hook)],
        input='{"status":"completed","loop_count":0}',
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert hooked.returncode == 0, hooked.stderr
    body = json.loads(hooked.stdout or "{}")
    assert "followup_message" not in body
    assert "no drift" not in hooked.stdout.lower()
