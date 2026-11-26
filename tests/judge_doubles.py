"""Scripted judge for offline fixtures. Not used by the product."""

from context_guard.judge import ScriptedJudge

# Maps the old homepage/migration fixture sentences to verdicts so the
# replay stays offline. The product code does not contain these needles.
FIXTURE_JUDGE = ScriptedJudge(
    "on_goal",
    when_contains=[
        ("note-taking app", "off_goal"),
        ("database migration", "off_goal"),
        ("Ignore the goal", "off_goal"),
        ("Do not continue the session model", "off_goal"),
    ],
)
