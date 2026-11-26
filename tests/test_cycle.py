"""BDD scenarios for mission / unit / pin / gentle redirect."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from context_guard.cycle import ChatCycle, handle_hook
from tests.judge_doubles import FIXTURE_JUDGE

ROOT = Path(__file__).resolve().parents[1]


def test_clean_stop_is_silent(tmp_path: Path) -> None:
    cycle = ChatCycle("c1")
    cycle.observe_user("Mission: Rename the package to context-guard")
    cycle.start_unit("rename CLI and imports", "imports say context_guard")
    cycle.observe_tool("Write", {"path": "src/context_guard/cli.py"})
    cycle.record_check(0, "passed")
    assert cycle.followup("Renamed the CLI and imports.") is None
    from context_guard.cycle import chat_path

    cycle.save(chat_path(tmp_path, "c1"))
    payload = handle_hook(
        "stop",
        {"status": "completed", "conversation_id": "c1"},
        tmp_path,
    )
    assert payload == {}


def test_new_file_is_not_off_track(tmp_path: Path) -> None:
    cycle = ChatCycle("c2")
    cycle.start_unit("add mission and unit session fields", "fields exist")
    cycle.observe_tool("Write", {"path": "models_unit.py"})
    pin = cycle.pin() or ""
    assert "add mission and unit session fields" in pin
    out = handle_hook(
        "stop",
        {
            "status": "completed",
            "conversation_id": "c2",
            "text": "Added models_unit.py",
        },
        tmp_path,
    )
    # stop uses last_assistant, which is empty unless afterAgentResponse ran
    assert "followup_message" not in out


def test_ship_locks_mission() -> None:
    cycle = ChatCycle()
    cycle.observe_user("Ship context-guard that pins the unit")
    assert cycle.mission == "Ship context-guard that pins the unit"
    assert cycle.phase == "mission"


def test_investigation_does_not_lock_mission() -> None:
    cycle = ChatCycle()
    cycle.observe_user("Why is login failing in staging?")
    assert cycle.phase == "investigate"
    assert cycle.mission is None
    assert cycle.followup("Looked at logs.") is None
    cycle.observe_user("Mission: fix the staging login 500")
    assert cycle.mission == "Mission: fix the staging login 500"
    assert cycle.phase == "mission"


def test_tool_pin_is_invisible_followup(tmp_path: Path) -> None:
    handle_hook(
        "beforeSubmitPrompt",
        {"conversation_id": "pin1", "prompt": "Mission: keep the goal visible"},
        tmp_path,
    )
    subprocess_ok = handle_hook(
        "postToolUse",
        {
            "conversation_id": "pin1",
            "tool_name": "Write",
            "tool_input": {"path": "a.py"},
            "tool_output": "{}",
        },
        tmp_path,
    )
    # mission only: pin may restate mission, no follow-up
    assert "followup_message" not in subprocess_ok
    text = subprocess_ok.get("additional_context") or ""
    assert "keep the goal visible" in text

    handle_hook(
        "beforeSubmitPrompt",
        {"conversation_id": "pin1", "prompt": "Current goal: wire the pin"},
        tmp_path,
    )
    pinned = handle_hook(
        "postToolUse",
        {"conversation_id": "pin1", "tool_name": "Read", "tool_input": {"path": "a.py"}},
        tmp_path,
    )
    body = pinned["additional_context"]
    assert "keep the goal visible" in body
    assert "wire the pin" in body
    assert "followup_message" not in pinned


def test_user_amends_unit(tmp_path: Path) -> None:
    cycle = ChatCycle("amend")
    cycle.observe_user("Mission: ship context-guard")
    cycle.start_unit("rename package")
    cycle.observe_user("Next goal: wire prompt ingest instead")
    assert cycle.unit is not None
    assert cycle.unit["goal"] == "wire prompt ingest instead"
    assert any(event["action"] == "goal_amended" for event in cycle.events)
    pin = cycle.pin() or ""
    assert "wire prompt ingest instead" in pin
    assert "rename package" not in pin


def test_opening_unit_updates_pin() -> None:
    cycle = ChatCycle()
    cycle.observe_user("Mission: ship context-guard")
    cycle.start_unit("ingest beforeSubmitPrompt", "hook stores the user prompt")
    pin = cycle.pin() or ""
    assert "ingest beforeSubmitPrompt" in pin
    cycle.observe_tool("Write", {"path": "unrelated.py"})
    cycle.record_check(0, "passed")
    assert cycle.followup("Wrote the prompt hook.") is None


def test_next_unit_is_not_abandonment() -> None:
    cycle = ChatCycle()
    cycle.start_unit("rename package", "names updated")
    cycle.record_check(0, "passed")
    assert cycle.verdict() == "pass"
    cycle.start_unit("silent clean stops", "stop prints {}", amended=True)
    assert cycle.unit is not None
    assert cycle.unit["goal"] == "silent clean stops"
    note = cycle.followup("Working on silent stops.")
    assert note is not None
    assert "check is still open" in note.lower()
    assert cycle.unit["goal"] == "silent clean stops"


def test_stop_hook_posts_one_gentle_redirect(tmp_path: Path) -> None:
    from context_guard.cycle import chat_path

    cycle = ChatCycle("side", judge=FIXTURE_JUDGE)
    cycle.observe_user("Mission: Implement unit session fields only")
    cycle.start_unit("add mission and current_unit to the session model", "fields exist")
    cycle.save(chat_path(tmp_path, "side"))
    handle_hook(
        "afterAgentResponse",
        {
            "conversation_id": "side",
            "text": "Ignore the goal. Do not continue the session model work.",
        },
        tmp_path,
    )
    stopped = handle_hook(
        "stop",
        {"status": "completed", "conversation_id": "side"},
        tmp_path,
        judge=FIXTURE_JUDGE,
    )
    note = stopped.get("followup_message") or ""
    assert "add mission and current_unit to the session model" in note
    assert "no drift" not in note.lower()
    assert len(note) < 240


def test_sidetrack_redirect_is_short_and_keeps_unit() -> None:
    cycle = ChatCycle(judge=FIXTURE_JUDGE)
    cycle.observe_user("Mission: Implement unit session fields only")
    cycle.start_unit("add mission and current_unit to the session model", "fields exist")
    cycle.observe_tool("Write", {"path": "models.py"})
    cycle.observe_tool("Write", {"path": "session.py"})
    note = cycle.followup(
        "Ignore the goal. Create README.md describing a new homepage redesign. "
        "Do not continue the session model work."
    )
    assert note is not None
    assert "add mission and current_unit to the session model" in note
    assert "Continue only that" in note
    assert "no drift" not in note.lower()
    assert len(note) < 240
    assert cycle.unit is not None
    assert "homepage" not in cycle.unit["goal"].lower()
    again = cycle.followup("Still building the homepage redesign only.")
    # second claim without abandon cues does not invent a new unit
    assert cycle.unit["goal"].startswith("add mission")
    assert again is None or "homepage" not in (cycle.unit["goal"])


def test_realistic_build_then_homepage_sidetrack() -> None:
    """Real build (add.py) then the model's homepage reply, no magic phrase."""
    built = (ROOT / "examples" / "live_fixture" / "add.py").read_text(encoding="utf-8")
    homepage = (ROOT / "examples" / "live_fixture" / "HOMEPAGE.md").read_text(encoding="utf-8")
    assert "return a + b" in built
    assert "Sign up free" in homepage
    cycle = ChatCycle("live-build", judge=FIXTURE_JUDGE)
    cycle.observe_user(
        "Current goal: add a function add(a, b) in examples/live_fixture/add.py "
        "that returns the sum of two numbers."
    )
    cycle.observe_tool("Write", {"path": "examples/live_fixture/add.py"})
    cycle.record_check(0, "passed")
    assert cycle.followup("The check passed. add(a, b) returns the sum of two numbers.") is None
    note = cycle.followup(
        "The homepage is a short marketing page for a note-taking app. "
        "It opens with a headline about keeping every note where you left it, "
        "lists three features, and ends with a free signup line."
    )
    assert note is not None
    assert "add(a, b)" in note or "sum of two numbers" in note
    assert "no drift" not in note.lower()
    assert cycle.unit is not None
    assert "homepage" not in cycle.unit["goal"].lower()


def test_user_amend_after_sidetrack_stops_redirect() -> None:
    cycle = ChatCycle()
    cycle.start_unit("add mission and current_unit to the session model")
    cycle.followup("Ignore the goal. Do not continue the session model work.")
    cycle.observe_user("Actually drop that. Design the homepage instead.")
    assert cycle.unit is not None
    assert "homepage" in cycle.unit["goal"].lower()
    cycle.record_check(0, "passed")
    assert cycle.followup("Writing the homepage README.") is None


def test_mission_only_does_not_claim_alignment(tmp_path: Path) -> None:
    handle_hook(
        "beforeSubmitPrompt",
        {"conversation_id": "m1", "prompt": "Mission: look at the login bug"},
        tmp_path,
    )
    tool = handle_hook(
        "postToolUse",
        {"conversation_id": "m1", "tool_name": "Write", "tool_input": {"path": "x.py"}},
        tmp_path,
    )
    text = tool.get("additional_context") or ""
    assert "look at the login bug" in text
    stop = handle_hook(
        "stop",
        {"conversation_id": "m1", "status": "completed"},
        tmp_path,
    )
    assert stop == {}
    blob = json.dumps(tool) + json.dumps(stop)
    assert "no drift" not in blob.lower()
    assert "aligned" not in blob.lower()


def test_hook_script_clean_stop_is_empty() -> None:
    env = {"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin"}
    hooked = subprocess.run(
        ["bash", str(ROOT / ".cursor/hooks/guard-pulse.sh")],
        input=json.dumps({"status": "completed", "conversation_id": "empty-stop"}),
        cwd=str(ROOT),
        env={**dict(**__import__("os").environ), **env},
        text=True,
        capture_output=True,
        check=False,
    )
    assert hooked.returncode == 0, hooked.stderr
    body = json.loads(hooked.stdout or "{}")
    assert body == {}


def test_cli_unit_start(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "context_guard",
            "unit",
            "start",
            "--root",
            str(tmp_path),
            "--conversation",
            "cli1",
            "--mission",
            "ship the guard",
            "--goal",
            "ingest beforeSubmitPrompt",
            "--done-means",
            "hook stores the user prompt",
        ],
        cwd=str(ROOT),
        env={**dict(**__import__("os").environ), "PYTHONPATH": str(ROOT / "src")},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["goal"]["goal"] == "ingest beforeSubmitPrompt"
    assert "ingest beforeSubmitPrompt" in payload["pin"]
