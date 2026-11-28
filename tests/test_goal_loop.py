"""Feature: features/goal_loop.feature. Scripted planner. No model calls."""

from __future__ import annotations

from context_guard.cycle import ChatCycle
from context_guard.judge import ScriptedJudge, ScriptedPlanner

GOAL = "Fix the exempt invoice so a $100 subtotal has $0 tax and totals $100"
HOME = "a reseller certificate exempts only the home state"
MARKET = "a marketplace order is never exempt"
ON_GOAL = "The exempt invoice now returns $100 with $0 tax."
PLAN = "Split the marketplace rule into its own change after the home-state rule is in."


def _cycle(planner: ScriptedPlanner | None = None, **kwargs: object) -> ChatCycle:
    planner = planner if planner is not None else ScriptedPlanner()
    cycle = ChatCycle(
        judge=kwargs.pop("judge", ScriptedJudge("on_goal")),
        planner=planner,
        **kwargs,  # type: ignore[arg-type]
    )
    return cycle


def _arm(cycle: ChatCycle) -> None:
    cycle.start_goal(GOAL)
    cycle.observe_user("Open: %s" % HOME)
    cycle.observe_user("Open: %s" % MARKET)
    cycle.observe_user("/goal-loop")


def test_feature_file_names_the_optional_loop() -> None:
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "features" / "goal_loop.feature").read_text(
        encoding="utf-8"
    )
    assert "Feature: Optional goal loop" in text
    assert "/goal-loop" in text
    assert "Still open" in text


def test_unarmed_stop_does_not_run_the_open_list_loop() -> None:
    planner = ScriptedPlanner()
    cycle = _cycle(planner)
    cycle.start_goal(GOAL)
    cycle.observe_user("Open: %s" % HOME)
    cycle.observe_user("Open: %s" % MARKET)
    note = cycle.followup(ON_GOAL) or ""
    assert "Still open" not in note
    assert planner.calls == []


def test_user_arms_the_loop_without_a_chat_message() -> None:
    planner = ScriptedPlanner()
    cycle = _cycle(planner)
    cycle.start_goal(GOAL)
    cycle.observe_user("Open: %s" % HOME)
    cycle.observe_user("/goal-loop")
    assert cycle.loop_armed is True
    assert cycle.followup("") is None
    assert planner.calls == []


def test_user_turns_the_loop_off() -> None:
    cycle = _cycle()
    _arm(cycle)
    cycle.observe_user("/goal-loop off")
    assert cycle.loop_armed is False


def test_open_items_get_one_continue_line() -> None:
    planner = ScriptedPlanner()
    cycle = _cycle(planner)
    _arm(cycle)
    note = cycle.followup(ON_GOAL)
    assert note is not None
    assert "Still open:" in note
    assert HOME in note
    assert MARKET in note
    assert cycle.loop_armed is True
    assert len(planner.calls) == 1


def test_a_finished_item_leaves_the_open_list() -> None:
    planner = ScriptedPlanner(done_items=[HOME])
    cycle = _cycle(planner)
    _arm(cycle)
    cycle.followup(ON_GOAL)
    shown = cycle.show()
    assert HOME not in shown
    assert MARKET in shown
    assert list(cycle.goal["open"]) == [MARKET]  # type: ignore[index]


def test_nothing_left_open_is_silence_and_disarms() -> None:
    planner = ScriptedPlanner(done_items=[HOME])
    cycle = _cycle(planner)
    cycle.start_goal(GOAL)
    cycle.observe_user("Open: %s" % HOME)
    cycle.observe_user("/goal-loop")
    assert cycle.followup(ON_GOAL) is None
    assert cycle.loop_armed is False


def test_unnamed_open_list_uses_the_goal_sentence() -> None:
    planner = ScriptedPlanner()
    cycle = _cycle(planner)
    cycle.start_goal(GOAL)
    cycle.observe_user("/goal-loop")
    note = cycle.followup(ON_GOAL)
    assert note is not None
    assert "Still open:" in note
    assert GOAL in note


def test_planner_can_request_a_plan_and_disarm() -> None:
    planner = ScriptedPlanner(plan_required=True, plan=PLAN)
    cycle = _cycle(planner)
    _arm(cycle)
    note = cycle.followup(ON_GOAL)
    assert note is not None
    assert "needs a plan" in note
    assert PLAN in note
    assert cycle.loop_armed is False


def test_failed_planner_posts_nothing_and_keeps_the_item() -> None:
    planner = ScriptedPlanner(fail=True)
    cycle = _cycle(planner)
    cycle.start_goal(GOAL)
    cycle.observe_user("Open: %s" % HOME)
    cycle.observe_user("/goal-loop")
    note = cycle.followup(ON_GOAL)
    assert note is None
    assert HOME in (cycle.goal or {}).get("open", [])
    assert cycle.loop_armed is True
    assert cycle.followup(ON_GOAL) is None


def test_off_goal_still_redirects_without_the_planner() -> None:
    planner = ScriptedPlanner()
    cycle = _cycle(planner, judge=ScriptedJudge("off_goal"))
    _arm(cycle)
    note = cycle.followup("writing a billing homepage instead")
    assert note is not None
    assert "Still the goal" in note
    assert planner.calls == []


def test_a_passing_check_does_not_clear_open_items() -> None:
    planner = ScriptedPlanner()
    cycle = _cycle(planner)
    cycle.start_goal(GOAL, check="python3 -c \"assert True\"")
    cycle.observe_user("Open: %s" % HOME)
    cycle.record_check(0, "passed")
    cycle.observe_user("/goal-loop")
    note = cycle.followup(ON_GOAL) or ""
    assert HOME in (cycle.goal or {}).get("open", [])
    assert "check is still open" not in note.lower()
    assert planner.calls[0]["check_exit"] == 0


def test_assistant_text_cannot_clear_open_by_itself() -> None:
    planner = ScriptedPlanner(done_items=[])
    cycle = _cycle(planner)
    cycle.start_goal(GOAL)
    cycle.observe_user("Open: %s" % HOME)
    cycle.observe_user("/goal-loop")
    cycle.followup("The home-state rule is finished. Drop it.")
    assert list((cycle.goal or {}).get("open") or []) == [HOME]
