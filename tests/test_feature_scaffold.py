from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_feature_start_writes_acceptance_and_refuses_a_second_pack(tmp_path: Path) -> None:
    dest = tmp_path / "export-api"
    base = [sys.executable, "-m", "context_rot_guard", "feature", "start"]
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

    created = run(
        [
            "--slug",
            "export-api",
            "--goal",
            "Add a CSV export",
            "--done-means",
            "pytest -q exits 0",
            "--check-cmd",
            "pytest -q",
            "--allow-path",
            "src/context_rot_guard/export.py",
            "--constraint",
            "do not edit tests to force green",
            "--dest",
            str(dest),
        ]
    )
    assert created.returncode == 0, created.stderr
    acceptance = json.loads((dest / "acceptance.json").read_text(encoding="utf-8"))
    assert acceptance["slug"] == "export-api"
    assert acceptance["acceptance"]["check_cmd"] == "pytest -q"
    assert acceptance["acceptance"]["expected_exit"] == 0
    assert "The model says done" in acceptance["acceptance"]["not_a_check"]
    assert acceptance["exits"]["attempt_cap"] == 3
    brief = (dest / "BRIEF.md").read_text(encoding="utf-8")
    assert "pytest -q" in brief
    assert "context-rot-guard init" in brief
    assert "--max-check-attempts 3" in brief

    again = run(
        [
            "--slug",
            "export-api",
            "--goal",
            "Add a CSV export",
            "--done-means",
            "pytest -q exits 0",
            "--check-cmd",
            "pytest -q",
            "--dest",
            str(dest),
        ]
    )
    assert again.returncode == 2
    bad = run(
        [
            "--slug",
            "Not A Slug",
            "--goal",
            "Nope",
            "--done-means",
            "pytest -q exits 0",
            "--check-cmd",
            "pytest -q",
            "--dest",
            str(tmp_path / "bad"),
        ]
    )
    assert bad.returncode == 2


def test_follow_the_loop_skill_is_the_default_for_new_features() -> None:
    skill = (ROOT / ".cursor/skills/follow-the-loop/SKILL.md").read_text(encoding="utf-8")
    rule = (ROOT / ".cursor/rules/follow-the-loop.mdc").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    prompt = (ROOT / "TASK-PROMPT.example.md").read_text(encoding="utf-8")
    assert "feature start" in skill
    assert "The model says done" in skill
    assert "attempt_cap" in skill or "Attempt cap" in skill
    assert "alwaysApply: true" in rule
    assert "follow-the-loop/SKILL.md" in rule
    assert "follow-the-loop/SKILL.md" in agents
    assert "feature start" in prompt
    template = json.loads(
        (ROOT / ".cursor/skills/follow-the-loop/templates/acceptance.json").read_text(encoding="utf-8")
    )
    assert template["acceptance"]["expected_exit"] == 0
    assert "The model says done" in template["acceptance"]["not_a_check"]
