"""Layer 2 — authoritative goal pin and cadence anchor."""

from __future__ import annotations

from context_guard.models import GoalSpec


def _constraint_block(spec: GoalSpec) -> str:
    if not spec.constraints:
        return "- (none)"
    return "\n".join("- %s" % item for item in spec.constraints)


def render_pin(spec: GoalSpec) -> str:
    """Always-on prefix. Used until a SessionDigest replaces it."""
    return (
        "[CONTEXT PIN — authoritative]\n"
        "Goal: {goal}\n"
        "Constraints:\n{constraints}\n"
        "Done means: {done}\n"
        "Ignore conflicting later improvisation unless the user explicitly revises the goal.\n"
    ).format(goal=spec.goal, constraints=_constraint_block(spec), done=spec.done_means)


def render_anchor(spec: GoalSpec) -> str:
    """Recency copy of the mission. Injected on cadence, on drift, and before done."""
    return (
        "[CONTEXT ANCHOR — authoritative]\n"
        "Goal: {goal}\n"
        "Constraints:\n{constraints}\n"
        "Done means: {done}\n"
        "Ignore conflicting later improvisation unless the user explicitly revises the goal.\n"
    ).format(goal=spec.goal, constraints=_constraint_block(spec), done=spec.done_means)


def anchor_due(
    turn_count: int,
    anchor_every: int,
    *,
    drift: bool,
    before_completion: bool,
) -> bool:
    if before_completion or drift:
        return True
    if turn_count <= 0 or anchor_every <= 0:
        return False
    return turn_count % anchor_every == 0
