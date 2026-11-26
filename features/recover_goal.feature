Feature: Recover a living goal from an existing chat
  As a developer who started a chat before naming a living goal
  I want context-guard to scan that chat and arm the goal and key details
  So an old conversation can be held to the same list as a new one

  # Spec: recover for chats that never used Current goal: / leading /goal.
  # User lines below are the user's words. No invented assistant reply.
  # Offline suite first; a real subagent run accepts the feature.

  Background:
    Given an existing chat has user prompts about the exempt-invoice fix
    And those prompts include the home-state reseller rule
    And those prompts include that a marketplace order is never exempt
    And no living goal is open
    And no prompt starts with Current goal: or a leading /goal

  Scenario: Recover arms the living goal from chat history
    When the user says Recover goal
    Then goal show prints a goal about the exempt invoice
    And goal show lists the home-state rule
    And goal show lists the marketplace rule
    And context-guard posts no "Still the goal" message from recover

  Scenario: After recover a green check stays silent
    Given the living goal was recovered from that chat
    And the check exited 0
    When the assistant reply is still about that invoice goal
    Then context-guard stays silent

  Scenario: A buried slash-goal is recovered without a model
    Given an existing chat stores a Cursor-wrapped /goal and Check line
    And no living goal is open
    When the user says Recover goal
    Then goal show prints that goal and that check

  # Rubric for a recovered summary. Each item is pass or fail.
  # The grade fails if any item fails.
  # Goal. One durable ask for the whole chat. The latest complaint about /show-goal is not the goal.
  # Coverage. Later rules that change the product are present: living goal from /goal, recover for an existing chat, silent when the check is green, one correction when the check is open or red, goal show lists held details, real subagent feature tests.
  # Precision. Every detail is supported by a user message. A cancelled requirement belongs under Rejected / cancelled, not Held. The on-the-fly mid-chat pulse must not appear as work to build.
  # Check. A Check: line only if the user named a command. python3 -m pytest -q may appear because it is this repo's named gate. No invented shell command.
  # Shape. After recover on a long chat, the summary uses briefing sections (Arc, Held now, Rejected / cancelled, Open as needed). Held items are requirements, not a transcript dump and not system or skill text. Rejected may name cancelled work such as the mid-chat pulse.
  # The live grade prints product goal show, then this rubric, then an external model score.
  # That runner is the named Check. A red grade stays on this goal. It does not open a new plan.

  Scenario: A summary that builds the cancelled pulse fails Precision
    Given a recovered summary lists an on-the-fly mid-chat pulse as work to build
    When the summary is graded
    Then the grade fails Precision

  Scenario: A summary that drops recover fails Coverage
    Given a recovered summary does not mention recover
    When the summary is graded
    Then the grade fails Coverage
