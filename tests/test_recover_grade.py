"""Rubric for a recovered summary. No model calls."""

from __future__ import annotations

from pathlib import Path

from context_guard.cycle import ChatCycle, chat_path
from context_guard.judge import RECOVER_RUBRIC, CursorModelGrader, ScriptedGrader

ROOT = Path(__file__).resolve().parents[1]


def test_feature_file_states_the_five_rubric_items() -> None:
    text = (ROOT / "features" / "recover_goal.feature").read_text(encoding="utf-8")
    for name in ("Goal.", "Coverage.", "Precision.", "Check.", "Shape."):
        assert name in text
        assert name in RECOVER_RUBRIC


def test_pulse_listed_as_work_fails_precision() -> None:
    shown = (
        "Keep a living goal and recover it for an existing chat\n"
        "- Add an on-the-fly mid-chat pulse that scans during the chat"
    )
    grade = ScriptedGrader().grade(dialogue=["build the pulse"], goal_show=shown, rubric=RECOVER_RUBRIC)
    assert grade["pass"] is False
    assert "Precision" in grade["fails"]


def test_dropping_recover_fails_coverage() -> None:
    shown = "Fix the exempt invoice\n- a marketplace order is never exempt"
    grade = ScriptedGrader().grade(dialogue=["recover the chat"], goal_show=shown, rubric=RECOVER_RUBRIC)
    assert grade["pass"] is False
    assert "Coverage" in grade["fails"]


def test_prohibition_of_the_pulse_is_not_a_precision_fail() -> None:
    shown = (
        "Recover a living goal from an existing chat\n"
        "Check: python3 -m pytest -q\n"
        "- Do not add a continuous mid-chat pulse"
    )
    grade = ScriptedGrader().grade(dialogue=["stop the pulse"], goal_show=shown, rubric=RECOVER_RUBRIC)
    assert grade["fails"] == []
    assert grade["pass"] is True


def test_pulse_under_rejected_is_not_a_precision_fail() -> None:
    shown = (
        "Keep a living goal and recover it for an existing chat\n"
        "## Held now\n"
        "- Silent when the check is green\n"
        "## Rejected / cancelled\n"
        "- The continuous mid-chat on-the-fly pulse; do not build it\n"
        "## Open\n"
        "- Grade the recover summary"
    )
    grade = ScriptedGrader().grade(dialogue=["cancel the pulse"], goal_show=shown, rubric=RECOVER_RUBRIC)
    assert grade["fails"] == []
    assert grade["pass"] is True


def test_cursor_grader_under_pytest_does_not_invent_a_pass() -> None:
    grade = CursorModelGrader().grade(
        dialogue=["/goal keep the living goal"],
        goal_show="keep the living goal",
        rubric=RECOVER_RUBRIC,
    )
    assert grade["available"] is False
    assert grade["pass"] is not True


def test_load_keeps_goal_when_the_file_has_trailing_bytes(tmp_path: Path) -> None:
    cid = "torn-sidecar"
    cycle = ChatCycle(cid)
    cycle.start_goal("keep this", check="python3 -m pytest -q")
    path = chat_path(tmp_path, cid)
    cycle.save(path)
    path.write_text(path.read_text(encoding="utf-8") + 'ature."\n}', encoding="utf-8")
    loaded = ChatCycle.load(path, cid)
    assert loaded.goal is not None
    assert loaded.goal["goal"] == "keep this"
    assert loaded.goal["check"] == "python3 -m pytest -q"
