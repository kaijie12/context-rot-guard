from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_demo_prints_compact_anchor_and_drift(capsys) -> None:
    path = ROOT / "examples" / "demo_drift_session.py"
    spec = importlib.util.spec_from_file_location("demo_drift_session", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main() == 0
    out = capsys.readouterr().out
    assert "before_messages=" in out
    assert "after_messages=" in out
    assert "DRIFT drift=true" in out
    assert "goal_verbatim=true" in out
    assert "done_status=blocked" in out
