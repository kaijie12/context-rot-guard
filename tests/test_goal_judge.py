"""Feature: stay on the exempt-invoice goal. The judge decides, not a word list."""

from __future__ import annotations

from context_guard.cycle import ChatCycle
from context_guard.judge import ScriptedJudge, UnavailableJudge

GOAL = (
    "Fix billing/invoice.py so an exempt customer with a $100 subtotal "
    "has $0 tax and a $100 total, and the existing invoice tests pass"
)
ON_GOAL = (
    "Exempt customers now have $0 tax on a $100 subtotal and the invoice tests passed."
)
OFF_GOAL = (
    "I rewrote the plan comparison table and the annual discount copy "
    "on the billing settings screen."
)


def test_reply_still_on_the_tax_bug_is_silent() -> None:
    cycle = ChatCycle(judge=ScriptedJudge("on_goal"))
    cycle.start_goal(GOAL)
    cycle.record_check(0, "passed")
    explained = cycle.explain_assistant(ON_GOAL)
    assert explained["judge"] == "on_goal"
    assert cycle.followup(ON_GOAL) is None


def test_nearby_billing_copy_is_off_goal_when_the_judge_says_so() -> None:
    cycle = ChatCycle(judge=ScriptedJudge("off_goal"))
    cycle.start_goal(GOAL)
    explained = cycle.explain_assistant(OFF_GOAL)
    assert explained["judge"] == "off_goal"
    note = cycle.followup(OFF_GOAL)
    assert note is not None
    assert "Still the goal:" in note
    assert "exempt customer" in note
    assert cycle.goal is not None
    assert cycle.goal["goal"] == GOAL


def test_shared_billing_word_does_not_redirect_without_the_judge() -> None:
    """The reply shares 'billing' with the goal. Silence unless the judge says off_goal."""
    cycle = ChatCycle(judge=ScriptedJudge("on_goal"))
    cycle.start_goal(GOAL)
    cycle.record_check(0, "passed")
    assert cycle.followup(OFF_GOAL) is None


def test_user_amend_then_copy_reply_is_silent() -> None:
    class _AfterAmend(ScriptedJudge):
        def judge(self, *, mission, goal, last_user, assistant):
            if "comparison" in (goal or "").lower():
                return {"verdict": "on_goal", "reason": "scripted"}
            return super().judge(
                mission=mission, goal=goal, last_user=last_user, assistant=assistant
            )

    cycle = ChatCycle(
        judge=_AfterAmend("on_goal", when_contains=[("plan comparison table", "off_goal")])
    )
    cycle.start_goal(GOAL)
    note = cycle.followup(OFF_GOAL)
    assert note is not None and "Still the goal:" in note
    cycle.observe_user(
        "Actually drop that. Rewrite the plan comparison table and the annual discount copy instead."
    )
    assert cycle.goal is not None
    assert "comparison" in cycle.goal["goal"].lower()
    cycle.record_check(0, "passed")
    assert cycle.followup("Rewrote the plan comparison table and the annual discount copy.") is None


def test_judge_unavailable_stays_silent() -> None:
    cycle = ChatCycle(judge=UnavailableJudge())
    cycle.start_goal(GOAL)
    explained = cycle.explain_assistant(OFF_GOAL)
    assert explained["judge"] == "unavailable"
    assert explained["action"] == "silence"
    note = cycle.followup(OFF_GOAL)
    assert note is None or "Still the goal" not in note
    assert "check is still open" not in (note or "").lower()
