"""Holistic live-chat fixture: hooks arm the unit, sidetrack redirects, amend clears it."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from context_guard.cycle import ChatCycle, chat_path, handle_hook
from tests.judge_doubles import FIXTURE_JUDGE

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "fixtures" / "live_chat.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_blind_sidecar_stays_silent(tmp_path: Path) -> None:
    data = _fixture()["sidecar_blind"]
    data = dict(data)
    data["conversation_id"] = "blind"
    path = chat_path(tmp_path, "blind")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    assert handle_hook("stop", {"conversation_id": "blind", "status": "completed"}, tmp_path) == {}


def test_live_chat_story(tmp_path: Path) -> None:
    fixture = _fixture()
    cid = "live-build"
    for turn in fixture["turns"]:
        expect = turn["expect"]
        if "hook" in turn:
            handle_hook(turn["hook"]["event"], turn["hook"]["payload"], tmp_path)
        if turn["id"] == "q1":
            cycle = ChatCycle.load(chat_path(tmp_path, cid), cid)
            assert cycle.phase == "investigate"
            assert cycle.mission is None
            assert handle_hook("stop", {"conversation_id": cid, "status": "completed"}, tmp_path) == {}
        if turn["id"] == "u1":
            cycle = ChatCycle.load(chat_path(tmp_path, cid), cid)
            assert cycle.unit is not None
            assert "add(a, b)" in cycle.unit["goal"]
            assert cycle.phase == "goal"
        for hook in turn.get("hooks") or []:
            if turn.get("check") and hook["event"] == "afterAgentResponse":
                cycle = ChatCycle.load(chat_path(tmp_path, cid), cid)
                cycle.record_check(int(turn["check"]["exit_code"]), turn["check"].get("output") or "")
                cycle.save(chat_path(tmp_path, cid))
            out = handle_hook(hook["event"], hook["payload"], tmp_path, judge=FIXTURE_JUDGE)
            if hook["event"] == "postToolUse" and turn["id"] == "build":
                pin = out.get("additional_context") or ""
                assert "add(a, b)" in pin
            if hook["event"] == "stop":
                if "followup_contains" in expect:
                    note = out.get("followup_message") or ""
                    for needle in expect["followup_contains"]:
                        assert needle.lower() in note.lower(), note
                    for bad in expect.get("followup_forbids") or []:
                        assert bad.lower() not in note.lower(), note
                    cycle = ChatCycle.load(chat_path(tmp_path, cid), cid)
                    assert cycle.unit is not None
                    assert expect["unit_contains"] in cycle.unit["goal"]
                    assert expect["unit_forbids"] not in cycle.unit["goal"].lower()
                elif expect.get("stop") == {}:
                    note = out.get("followup_message") or ""
                    assert "Still the goal" not in note
                    assert "check is still open" not in note.lower()
                    if not note:
                        assert out == {}
        if turn["id"] == "amend":
            cycle = ChatCycle.load(chat_path(tmp_path, cid), cid)
            assert cycle.unit is not None
            assert "homepage" in cycle.unit["goal"].lower()


def test_migration_sidetrack_and_false_redirect() -> None:
    limits = _fixture()["limits"]
    cycle = ChatCycle("lim", judge=FIXTURE_JUDGE)
    cycle.start_unit("add a function add(a, b) that returns the sum of two numbers")
    note = cycle.followup(limits["migration_sidetrack"])
    assert note is not None and "Still the goal" in note
    cycle.record_check(0, "passed")
    assert cycle.followup(limits["stayed_on_goal"]) is None


def test_before_submit_prompt_hook_script_arms_unit(tmp_path: Path) -> None:
    env = {**dict(**__import__("os").environ), "PYTHONPATH": str(ROOT / "src")}
    payload = {
        "conversation_id": "hook-arm",
        "prompt": "Current goal: wire prompt ingest from the hook",
    }
    # Isolate sidecar under tmp by using --root via python module (script uses repo root).
    # Call the library path the script wraps:
    out = handle_hook("beforeSubmitPrompt", payload, tmp_path)
    assert out == {}
    cycle = ChatCycle.load(chat_path(tmp_path, "hook-arm"), "hook-arm")
    assert cycle.unit is not None
    assert "wire prompt ingest" in cycle.unit["goal"]


def test_verify_script_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "verify_live_story.py")],
        cwd=str(ROOT),
        env={**dict(**__import__("os").environ), "PYTHONPATH": str(ROOT / "src")},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "PASS unit check" in result.stdout
    assert "PASS product behavior" in result.stdout
    assert "PASS story match" in result.stdout
