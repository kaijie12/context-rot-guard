"""Optional live mark: shells out to the Composer 2.5 Fast feature runner."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "examples" / "run_stay_on_unit_live.py"


@pytest.mark.live
def test_stay_on_unit_live_runner() -> None:
    env = os.environ.copy()
    result = subprocess.run(
        [sys.executable, str(RUNNER)],
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
