Feature: Stay on the current unit
  As a developer in a coding chat
  I want context-guard to stay quiet while the agent works the unit
  And speak once if the agent leaves that unit
  So the chat stays on the ask without status spam

  How to run this feature (live model every time):
    python3 examples/run_stay_on_unit_live.py
  That starts Composer 2.5, builds add(a, b), then sidetracks to a homepage,
  then applies context-guard to those fresh replies and writes examples/live-run-log.json.
  Requires cursor-sdk + CURSOR_API_KEY in env or ~/.zshrc (Python >= 3.10). Does not fall back to the fixture.

  Offline gate (no model):
    python3 -m pytest -q
    python3 examples/verify_live_story.py
  Optional inside pytest: pytest -m live  (shells out to the live runner; excluded by default)

  Scenario: Live chat — question, unit, build, sidetrack, amend
    Given a fresh Composer 2.5 chat from examples/run_stay_on_unit_live.py
    When turn 1 builds add(a, b) in examples/live_fixture/add.py and the check passes
    Then the on-unit product follow-up is empty
    When turn 2 writes examples/live_fixture/HOMEPAGE.md and describes only that page
    Then one short followup restates the add unit and does not say no drift
    And the unit string is still the add unit after the homepage reply
    # Offline replay of the same story (fixture): examples/fixtures/live_chat.json
    Given the transcript in examples/fixtures/live_chat.json
    When the user asks why add() does not exist yet
    Then the product records only and stop stays empty
    When the user sets Current unit to add(a, b) in examples/live_fixture/add.py
    Then the unit is armed with no chat message
    When the agent writes add.py and the check passes
    Then stop stays empty and the pin still quotes add(a, b)
    When the agent describes a marketing homepage with a signup line
    Then one short followup restates the add unit and does not say no drift
    And the unit string is not replaced by homepage
    When the user says Actually drop that. Design the homepage instead
    Then the unit amends and a later homepage reply stays quiet

  Scenario: Sidetrack that is not a homepage still redirects
    Given an open unit about add(a, b)
    When the assistant says it wrote a database migration for the billing schema instead
    Then context-guard posts Still the unit

  Scenario: Saying you stayed on the unit does not redirect
    Given an open unit about add(a, b)
    When the assistant says it did not write a marketing page and the open unit is still the add function
    Then stop stays empty
