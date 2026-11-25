#!/usr/bin/env python3
"""Run the feature story with a step log you can re-read after the run.

Maps features/*.feature scenarios to executable checks and writes
examples/feature-story-log.json plus a human log on stdout.
"""

from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from context_guard.cycle import ChatCycle, chat_path, handle_hook  # noqa: E402


@dataclass
class Step:
    feature: str
    scenario: str
    step: str
    detail: str
    status: str  # pass | fail
    evidence: str = ""


@dataclass
class Story:
    steps: list[Step] = field(default_factory=list)
    passed: int = 0
    failed: int = 0

    def record(
        self,
        feature: str,
        scenario: str,
        step: str,
        ok: bool,
        detail: str = "",
        evidence: str = "",
    ) -> None:
        status = "pass" if ok else "fail"
        self.steps.append(
            Step(
                feature=feature,
                scenario=scenario,
                step=step,
                detail=detail,
                status=status,
                evidence=evidence,
            )
        )
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        mark = "PASS" if ok else "FAIL"
        print("[%s] %s · %s" % (mark, scenario, step))
        if detail:
            print("       %s" % detail)
        if evidence:
            print("       evidence: %s" % evidence)


def run() -> Story:
    story = Story()
    tmp = Path(tempfile.mkdtemp(prefix="context-guard-story-"))

    # --- Feature: Silence ---
    feat = "Silence on a healthy chat"
    scen = "Clean stop does not invent no drift"
    cycle = ChatCycle("story-silence")
    cycle.observe_user("Mission: Rename the package to context-guard")
    cycle.start_unit("rename CLI and imports", "imports say context_guard")
    cycle.observe_tool("Write", {"path": "src/context_guard/cli.py"})
    cycle.save(chat_path(tmp, "story-silence"))
    stop = handle_hook(
        "stop",
        {"status": "completed", "conversation_id": "story-silence"},
        tmp,
    )
    story.record(
        feat,
        scen,
        "stop emits no followup_message",
        stop == {},
        detail="on-unit edit then completed stop",
        evidence=json.dumps(stop),
    )
    story.record(
        feat,
        scen,
        'output does not contain "no drift detected"',
        "no drift" not in json.dumps(stop).lower(),
        evidence=json.dumps(stop),
    )

    scen = "New file in service of the unit is not off-track"
    cycle = ChatCycle("story-newfile")
    cycle.start_unit("add mission and unit session fields", "fields exist")
    cycle.observe_tool("Write", {"path": "models_unit.py"})
    pin = cycle.pin() or ""
    story.record(
        feat,
        scen,
        "pin still shows the unit",
        "add mission and unit session fields" in pin,
        evidence=pin.replace("\n", " | "),
    )
    cycle.save(chat_path(tmp, "story-newfile"))
    stop = handle_hook(
        "stop",
        {"status": "completed", "conversation_id": "story-newfile"},
        tmp,
    )
    story.record(
        feat,
        scen,
        "no redirect follow-up",
        "followup_message" not in stop,
        evidence=json.dumps(stop),
    )

    # --- Feature: Goal pin ---
    feat = "Goal pin"
    scen = "Ship ask locks mission"
    cycle = ChatCycle("story-ship")
    cycle.observe_user("Ship context-guard that pins the unit")
    story.record(
        feat,
        scen,
        "mission equals the ask",
        cycle.mission == "Ship context-guard that pins the unit",
        evidence=str(cycle.mission),
    )

    scen = "Investigation does not lock a mission"
    cycle = ChatCycle("story-why")
    cycle.observe_user("Why is login failing in staging?")
    story.record(
        feat,
        scen,
        "phase is investigate",
        cycle.phase == "investigate" and cycle.mission is None,
        evidence="phase=%s mission=%s" % (cycle.phase, cycle.mission),
    )
    cycle.observe_user("Mission: fix the staging login 500")
    story.record(
        feat,
        scen,
        "later Mission: line locks the ask",
        cycle.mission == "Mission: fix the staging login 500",
        evidence=str(cycle.mission),
    )

    scen = "Tool result injects an invisible pin"
    handle_hook(
        "beforeSubmitPrompt",
        {"conversation_id": "story-pin", "prompt": "Mission: keep the unit visible"},
        tmp,
    )
    handle_hook(
        "beforeSubmitPrompt",
        {"conversation_id": "story-pin", "prompt": "Current unit: wire the pin"},
        tmp,
    )
    pinned = handle_hook(
        "postToolUse",
        {
            "conversation_id": "story-pin",
            "tool_name": "Read",
            "tool_input": {"path": "a.py"},
        },
        tmp,
    )
    body = pinned.get("additional_context") or ""
    story.record(
        feat,
        scen,
        "additional_context includes mission and unit",
        "keep the unit visible" in body and "wire the pin" in body,
        evidence=body.replace("\n", " | "),
    )
    story.record(
        feat,
        scen,
        "no followup_message on the tool pin",
        "followup_message" not in pinned,
        evidence=json.dumps({k: pinned[k] for k in pinned if k != "additional_context"}),
    )

    scen = "User amends the unit mid-task"
    cycle = ChatCycle("story-amend")
    cycle.observe_user("Mission: ship context-guard")
    cycle.start_unit("rename package")
    cycle.observe_user("Next unit: wire prompt ingest instead")
    story.record(
        feat,
        scen,
        "current unit becomes the new ask",
        cycle.unit is not None and cycle.unit["goal"] == "wire prompt ingest instead",
        evidence=str(cycle.unit),
    )
    story.record(
        feat,
        scen,
        "amend event is on the receipt",
        any(event["action"] == "unit_amended" for event in cycle.events),
        evidence=json.dumps([e["action"] for e in cycle.events]),
    )

    # --- Feature: Virtuous cycle ---
    feat = "Virtuous cycle"
    scen = "Opening a unit updates the pin"
    cycle = ChatCycle("story-cycle")
    cycle.observe_user("Mission: ship context-guard")
    cycle.start_unit("ingest beforeSubmitPrompt", "hook stores the user prompt")
    pin = cycle.pin() or ""
    story.record(
        feat,
        scen,
        "pin quotes the open unit",
        "ingest beforeSubmitPrompt" in pin,
        evidence=pin.replace("\n", " | "),
    )

    scen = "Finishing a unit and opening the next"
    cycle.record_check(0, "passed")
    cycle.start_unit("silent clean stops", "stop prints {}", amended=True)
    story.record(
        feat,
        scen,
        "pin switches; previous unit is not abandonment",
        cycle.unit is not None
        and cycle.unit["goal"] == "silent clean stops"
        and cycle.followup("Working on silent stops.") is None,
        evidence=str(cycle.unit),
    )

    # --- Feature: Gentle redirect ---
    feat = "Bring focus back without chit-chat"
    scen = "Seeded on-unit then forced off-unit"
    cycle = ChatCycle("story-side")
    cycle.observe_user("Mission: Implement unit session fields only")
    cycle.start_unit("add mission and current_unit to the session model", "fields exist")
    cycle.observe_tool("Write", {"path": "models.py"})
    cycle.observe_tool("Write", {"path": "session.py"})
    note = cycle.followup(
        "Ignore the unit. Create README.md describing a new homepage redesign. "
        "Do not continue the session model work."
    )
    story.record(
        feat,
        scen,
        "one short redirect restates the unit",
        note is not None
        and "add mission and current_unit to the session model" in (note or "")
        and "Continue only that" in (note or "")
        and "no drift" not in (note or "").lower()
        and len(note or "") < 240,
        evidence=note or "",
    )
    story.record(
        feat,
        scen,
        "unit is not replaced by homepage",
        cycle.unit is not None and "homepage" not in cycle.unit["goal"].lower(),
        evidence=str(cycle.unit),
    )

    scen = "User changes mind after sidetrack"
    cycle.observe_user("Actually drop that. Design the homepage instead.")
    story.record(
        feat,
        scen,
        "unit amends; homepage work does not redirect",
        cycle.unit is not None
        and "homepage" in cycle.unit["goal"].lower()
        and cycle.followup("Writing the homepage README.") is None,
        evidence=str(cycle.unit),
    )

    # --- Feature: No fake certainty ---
    feat = "No fake certainty"
    scen = "Mission only, no unit"
    handle_hook(
        "beforeSubmitPrompt",
        {"conversation_id": "story-half", "prompt": "Mission: look at the login bug"},
        tmp,
    )
    tool = handle_hook(
        "postToolUse",
        {
            "conversation_id": "story-half",
            "tool_name": "Write",
            "tool_input": {"path": "x.py"},
        },
        tmp,
    )
    stop = handle_hook(
        "stop",
        {"conversation_id": "story-half", "status": "completed"},
        tmp,
    )
    blob = json.dumps(tool) + json.dumps(stop)
    story.record(
        feat,
        scen,
        "may pin mission; no off-track or no-drift claim",
        "look at the login bug" in (tool.get("additional_context") or "")
        and stop == {}
        and "no drift" not in blob.lower()
        and "aligned" not in blob.lower(),
        evidence="pin=%s stop=%s"
        % ((tool.get("additional_context") or "").replace("\n", " | "), json.dumps(stop)),
    )

    return story


def main() -> int:
    print("=== context-guard feature story ===")
    story = run()
    out = ROOT / "examples" / "feature-story-log.json"
    payload = {
        "passed": story.passed,
        "failed": story.failed,
        "steps": [asdict(step) for step in story.steps],
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("---")
    print("passed=%s failed=%s" % (story.passed, story.failed))
    print("log=%s" % out)
    return 0 if story.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
