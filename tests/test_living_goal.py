"""Feature: living goal plus a check the loop can fail. No model calls."""

from __future__ import annotations

from context_guard.cycle import ChatCycle
from context_guard.judge import ScriptedExtractor, ScriptedJudge

GOAL = "Fix the exempt invoice so a $100 subtotal has $0 tax and totals $100"
CHECK = "python3 -c \"assert True\""
HOME = "a reseller certificate exempts only the home state"
MARKET = "a marketplace order is never exempt"
ON_GOAL = "The exempt invoice now returns $100 with $0 tax."


def _cycle(**kwargs: object) -> ChatCycle:
    cycle = ChatCycle(judge=ScriptedJudge("on_goal"), **kwargs)  # type: ignore[arg-type]
    return cycle


def test_slash_goal_in_a_cursor_wrapper_arms_that_chat() -> None:
    cycle = _cycle()
    wrapper = (
        "Skill Name: goal\nAccept `/goal <objective>`.\n"
        "<user_query>\n/goal %s\nCheck: %s\n</user_query>"
    ) % (GOAL, CHECK)
    cycle.observe_user(wrapper)
    shown = cycle.show()
    assert GOAL in shown
    assert CHECK in shown
    assert "<user_query>" not in (cycle.goal or {}).get("goal", "")
    assert "Accept" not in (cycle.goal or {}).get("goal", "")


def test_mentioning_slash_goal_inside_a_sentence_does_not_arm() -> None:
    cycle = _cycle()
    cycle.observe_user(
        "<user_query>\nthe /goal is for silent help in every chat\n</user_query>"
    )
    assert cycle.show() == "No goal."


def test_name_goal_and_check_is_visible_and_silent() -> None:
    cycle = _cycle()
    cycle.observe_user("Current goal: %s\nCheck: %s" % (GOAL, CHECK))
    shown = cycle.show()
    assert GOAL in shown
    assert CHECK in shown
    assert cycle.followup("") is not None
    assert "Still the goal" not in (cycle.followup("") or "")
    # Naming the goal posts no chat message. The loop speaks only after a reply
    # with no check. The pin is not a chat message.
    assert cycle.pin()
    assert "Still the goal" not in (cycle.pin() or "")


def test_later_details_show_up_without_a_scold() -> None:
    cycle = _cycle(
        extractor=ScriptedExtractor(
            [
                ("reseller certificate", "add", HOME),
                ("marketplace order", "add", MARKET),
            ]
        )
    )
    cycle.start_goal(GOAL, check=CHECK)
    cycle.observe_user("A reseller certificate exempts only the home state.")
    cycle.observe_user("A marketplace order is never exempt.")
    shown = cycle.show()
    assert GOAL in shown
    assert HOME in shown
    assert MARKET in shown
    assert cycle.followup("") is None or "Still the goal" not in (cycle.followup("") or "")


def test_a_question_does_not_change_the_goal_or_redirect() -> None:
    cycle = _cycle(extractor=ScriptedExtractor())
    cycle.start_goal(GOAL, check=CHECK)
    cycle._add_detail(HOME)
    cycle._add_detail(MARKET)
    before = cycle.show()
    cycle.observe_user(
        "Anything else in the folder that would mislead someone about tax?"
    )
    assert cycle.show() == before
    note = cycle.followup(ON_GOAL)
    assert note is None or "Still the goal" not in note


def test_drop_removes_one_detail_without_a_scold() -> None:
    cycle = _cycle(
        extractor=ScriptedExtractor(
            [("marketplace", "drop", MARKET)],
        )
    )
    cycle.start_goal(GOAL, check=CHECK)
    cycle._add_detail(HOME)
    cycle._add_detail(MARKET)
    cycle.observe_user("Actually drop that. The marketplace rule no longer applies.")
    shown = cycle.show()
    assert MARKET not in shown
    assert HOME in shown
    assert "Still the goal" not in shown


def test_missing_check_is_a_loop_correction() -> None:
    cycle = _cycle()
    cycle.start_goal(GOAL, check=CHECK)
    note = cycle.followup(ON_GOAL)
    assert note is not None
    assert "check is still open" in note.lower()
    assert GOAL in note
    assert "Stay on that goal" in note
    assert "Still the goal" not in note


def test_one_red_check_quotes_the_failure() -> None:
    cycle = _cycle()
    cycle.start_goal(GOAL, check=CHECK)
    cycle.record_check(1, "AssertionError: total was 108")
    note = cycle.followup(ON_GOAL)
    assert note is not None
    assert "AssertionError: total was 108" in note
    assert "Stay on that goal" in note
    assert "Stop and replan" not in note


def test_repeated_failure_stops_and_replans() -> None:
    cycle = _cycle()
    cycle.start_goal(GOAL, check=CHECK)
    cycle.record_check(1, "AssertionError: total was 108")
    cycle.record_check(1, "AssertionError: total was 108")
    before = cycle.show()
    note = cycle.followup(ON_GOAL)
    assert note is not None
    assert "Stop and replan. Goal still:" in note
    assert cycle.show() == before


def test_passing_check_is_silent() -> None:
    cycle = _cycle()
    cycle.start_goal(GOAL, check=CHECK)
    cycle.record_check(0, "passed")
    assert cycle.followup(ON_GOAL) is None


def test_an_answer_to_a_question_is_not_a_redirect() -> None:
    cycle = ChatCycle(judge=ScriptedJudge("off_goal"), extractor=ScriptedExtractor())
    cycle.start_goal(GOAL, check=CHECK)
    cycle.record_check(0, "passed")
    cycle.observe_user("Anything else in the folder that would mislead someone about tax?")
    note = cycle.followup("BILLING_COPY.md is about the annual discount, not tax.")
    assert note is None or "Still the goal" not in note


def test_off_goal_verdict_quotes_the_late_details() -> None:
    cycle = ChatCycle(judge=ScriptedJudge("off_goal"))
    cycle.start_goal(GOAL, check=CHECK)
    cycle._add_detail(HOME)
    cycle._add_detail(MARKET)
    note = cycle.followup("working on something else")
    assert note is not None
    assert "Still the goal" in note
    assert HOME in note
    assert MARKET in note
    assert cycle.goal is not None
    assert cycle.goal["goal"] == GOAL
    assert HOME in cycle.goal["details"]
