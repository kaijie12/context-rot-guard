#!/usr/bin/env python3
"""Product-in-use gate: unit check + product behavior + story/diagram match."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_guard.cycle import ChatCycle, chat_path, handle_hook  # noqa: E402
from context_guard.judge import ScriptedJudge  # noqa: E402

# Offline stand-in for the fixture sentences. The product judge is a model.
FIXTURE_JUDGE = ScriptedJudge(
    "on_goal",
    when_contains=[
        ("note-taking app", "off_goal"),
        ("database migration", "off_goal"),
        ("Ignore the goal", "off_goal"),
        ("Do not continue the session model", "off_goal"),
    ],
)

FIXTURE = ROOT / "examples" / "fixtures" / "live_chat.json"
LOG = ROOT / "examples" / "live-build-log.json"


def fail(message: str) -> int:
    print("FAIL: %s" % message, file=sys.stderr)
    return 1


def run_unit_check(spec: dict) -> int:
    command = spec["unit_check"]["command"]
    result = subprocess.run(
        command,
        shell=True,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return fail("unit check exit %s: %s" % (result.returncode, result.stderr or result.stdout))
    print("PASS unit check: %s" % command)
    return 0


def play_turns(tmp: Path, turns: list[dict]) -> list[dict]:
    lanes = []
    for turn in turns:
        expect = turn.get("expect") or {}
        if "hook" in turn:
            handle_hook(turn["hook"]["event"], turn["hook"]["payload"], tmp)
        for hook in turn.get("hooks") or []:
            if turn.get("check") and hook["event"] == "afterAgentResponse":
                cycle = ChatCycle.load(chat_path(tmp, "live-build"), "live-build")
                cycle.record_check(int(turn["check"]["exit_code"]), turn["check"].get("output") or "")
                cycle.save(chat_path(tmp, "live-build"))
            out = handle_hook(hook["event"], hook["payload"], tmp, judge=FIXTURE_JUDGE)
            if hook["event"] == "stop":
                turn["_stop"] = out
        cycle = ChatCycle.load(chat_path(tmp, "live-build"), "live-build")
        product = expect.get("product") or ""
        if "followup_contains" in expect:
            stop = turn.get("_stop") or {}
            note = stop.get("followup_message") or ""
            product = note or product
        elif expect.get("stop") == {}:
            product = expect.get("product") or "Quiet stop."
        lanes.append({"chat": turn["chat"], "product": product})
    return lanes


def assert_behavior(tmp: Path, fixture: dict) -> int:
    # Hook blindness: empty prompts stay silent.
    blind_path = chat_path(tmp, "blind")
    ChatCycle.from_dict(fixture["sidecar_blind"]).save(blind_path)
    # overwrite id
    data = json.loads(blind_path.read_text(encoding="utf-8"))
    data["conversation_id"] = "blind"
    blind_path.write_text(json.dumps(data), encoding="utf-8")
    stop = handle_hook("stop", {"conversation_id": "blind", "status": "completed"}, tmp)
    if stop != {}:
        return fail("blind sidecar should stay silent, got %s" % stop)

    lanes = play_turns(tmp, fixture["turns"])
    cycle = ChatCycle.load(chat_path(tmp, "live-build"), "live-build")

    for turn in fixture["turns"]:
        expect = turn["expect"]
        if expect.get("phase") and cycle.phase != expect["phase"] and turn["id"] in {"q1"}:
            # only check q1 phase immediately after that turn — re-play stepwise
            pass

    # Re-run stepwise for precise asserts
    work = Path(tmp / "assert")
    work.mkdir(parents=True, exist_ok=True)
    for turn in fixture["turns"]:
        expect = turn["expect"]
        if "hook" in turn:
            handle_hook(turn["hook"]["event"], turn["hook"]["payload"], work)
        if turn["id"] == "q1":
            c = ChatCycle.load(chat_path(work, "live-build"), "live-build")
            if c.phase != "investigate" or c.mission is not None:
                return fail("q1 should stay investigate, got phase=%s mission=%s" % (c.phase, c.mission))
            stop = handle_hook("stop", {"conversation_id": "live-build", "status": "completed"}, work)
            if stop != {}:
                return fail("q1 stop should be empty")
        if turn["id"] == "u1":
            c = ChatCycle.load(chat_path(work, "live-build"), "live-build")
            if not c.unit or "add(a, b)" not in c.unit["goal"]:
                return fail("u1 did not arm unit via beforeSubmitPrompt: %s" % c.unit)
        for hook in turn.get("hooks") or []:
            if turn.get("check") and hook["event"] == "afterAgentResponse":
                c = ChatCycle.load(chat_path(work, "live-build"), "live-build")
                c.record_check(int(turn["check"]["exit_code"]), turn["check"].get("output") or "")
                c.save(chat_path(work, "live-build"))
            out = handle_hook(hook["event"], hook["payload"], work, judge=FIXTURE_JUDGE)
            if hook["event"] == "stop":
                if "followup_contains" in expect:
                    note = out.get("followup_message") or ""
                    for needle in expect["followup_contains"]:
                        if needle.lower() not in note.lower():
                            return fail("missing %r in redirect: %s" % (needle, note))
                    for bad in expect.get("followup_forbids") or []:
                        if bad.lower() in note.lower():
                            return fail("forbidden %r in redirect: %s" % (bad, note))
                    c = ChatCycle.load(chat_path(work, "live-build"), "live-build")
                    if expect.get("unit_contains") and (
                        not c.unit or expect["unit_contains"] not in c.unit["goal"]
                    ):
                        return fail("unit lost after sidetrack: %s" % c.unit)
                    if expect.get("unit_forbids") and c.unit and expect["unit_forbids"] in c.unit["goal"].lower():
                        return fail("unit replaced by sidetrack: %s" % c.unit)
                elif expect.get("stop") == {}:
                    note = out.get("followup_message") or ""
                    if note and (
                        "check is still open" not in note.lower() or "Still the goal" in note
                    ):
                        return fail("%s expected quiet stop or an open check, got %s" % (turn["id"], out))
                    if not note and out != {}:
                        return fail("%s expected quiet stop, got %s" % (turn["id"], out))
        if turn["id"] == "amend":
            c = ChatCycle.load(chat_path(work, "live-build"), "live-build")
            if not c.unit or "homepage" not in c.unit["goal"].lower():
                return fail("amend did not switch unit: %s" % c.unit)

    # Limit cases
    limits = fixture["limits"]
    c = ChatCycle("limits", judge=FIXTURE_JUDGE)
    c.start_unit("add a function add(a, b) that returns the sum of two numbers")
    note = c.followup(limits["migration_sidetrack"])
    if not note or "Still the goal" not in note:
        return fail("migration sidetrack should redirect, got %s" % note)
    c.record_check(0, "passed")
    note = c.followup(limits["stayed_on_goal"])
    if note is not None:
        return fail("stayed-on-goal should be silent, got %s" % note)

    m = ChatCycle("mission-only")
    handle_hook(
        "beforeSubmitPrompt",
        {"conversation_id": "mission-only", "prompt": limits["mission_only_prompt"]},
        work,
    )
    pin = handle_hook(
        "postToolUse",
        {"conversation_id": "mission-only", "tool_name": "Write", "tool_input": {"path": "x.py"}},
        work,
    )
    stop = handle_hook(
        "stop",
        {"conversation_id": "mission-only", "status": "completed"},
        work,
    )
    text = (pin.get("additional_context") or "") + json.dumps(stop)
    if "look at the login bug" not in (pin.get("additional_context") or ""):
        return fail("mission-only should pin mission")
    if stop != {} or "no drift" in text.lower() or "aligned" in text.lower():
        return fail("mission-only must not claim alignment: %s" % text)

    LOG.write_text(
        json.dumps(
            {
                "lanes": lanes,
                "redirect": next(
                    (lane["product"] for lane in lanes if "Still the goal" in lane["product"]),
                    None,
                ),
                "add_py": fixture["files"]["add_py"],
                "homepage": fixture["files"]["homepage"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("PASS product behavior (%s lanes)" % len(lanes))
    return 0


def assert_story_match(fixture: dict) -> int:
    if not LOG.is_file():
        return fail("missing %s" % LOG)
    log = json.loads(LOG.read_text(encoding="utf-8"))
    expected = [turn["chat"] for turn in fixture["turns"]]
    got = [lane["chat"] for lane in log.get("lanes") or []]
    if expected != got:
        return fail("story chat lanes drifted\nexpected=%s\ngot=%s" % (expected, got))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for lane in log["lanes"]:
        # diagram must mention each product decision fragment or chat cue
        cue = "Still the goal" if "Still the goal" in lane["product"] else None
        if cue and cue not in readme:
            return fail("README diagram missing redirect cue")
    cues = (
        "Name the goal",
        "Later detail",
        "Question",
        "On-track",
        "Silence",
        "Still the goal",
        "exempt",
    )
    missing = [cue for cue in cues if cue not in readme]
    if missing:
        return fail("README diagram missing cues: %s" % ", ".join(missing))
    print("PASS story match: log lanes == fixture chats; README has the diagram cues")
    return 0


def main() -> int:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    add_py = ROOT / fixture["files"]["add_py"]
    homepage = ROOT / fixture["files"]["homepage"]
    if not add_py.is_file() or "return a + b" not in add_py.read_text(encoding="utf-8"):
        return fail("missing real add.py fixture")
    if not homepage.is_file() or "Sign up free" not in homepage.read_text(encoding="utf-8"):
        return fail("missing real HOMEPAGE.md fixture")

    import tempfile

    with tempfile.TemporaryDirectory(prefix="cg-verify-") as raw:
        tmp = Path(raw)
        code = run_unit_check(fixture)
        if code:
            return code
        code = assert_behavior(tmp, fixture)
        if code:
            return code
    # story match after README is updated — caller may run twice
    return assert_story_match(fixture)


if __name__ == "__main__":
    raise SystemExit(main())
