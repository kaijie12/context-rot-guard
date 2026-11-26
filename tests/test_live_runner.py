"""Optional live mark: shells out to Composer 2.5 feature runners."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STAY_RUNNER = ROOT / "examples" / "run_stay_on_unit_live.py"
RECOVER_RUNNER = ROOT / "examples" / "run_recover_goal_live.py"
GRADE_RUNNER = ROOT / "examples" / "run_recover_grade_live.py"


def _run_live(runner: Path) -> None:
    env = os.environ.copy()
    env.pop("PYTEST_CURRENT_TEST", None)
    result = subprocess.run(
        [sys.executable, str(runner)],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(
            "live runner exit %s\nstdout:\n%s\nstderr:\n%s"
            % (result.returncode, result.stdout, result.stderr)
        )


@pytest.mark.live
def test_stay_on_goal_live_runner() -> None:
    _run_live(STAY_RUNNER)


@pytest.mark.live
def test_recover_goal_live_runner() -> None:
    _run_live(RECOVER_RUNNER)


@pytest.mark.live
def test_recover_grade_live_runner() -> None:
    _run_live(GRADE_RUNNER)
