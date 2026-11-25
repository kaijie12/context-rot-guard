Feature: Stay on the current unit
  As a developer in a coding chat
  I want context-guard quiet while the agent works the unit
  And one short redirect only if that unit is abandoned
  So the chat stays on the ask without status spam

  # ── Who decides what ─────────────────────────────────────────
  # Mission / unit come from the USER (or CLI), never from the model:
  #   "Current unit: …"  "Mission: …"  "Actually drop that. …"
  # Sidetrack of the MODEL is detected by context-guard on assistant text:
  #   other-work cues (homepage, migration, …) without unit words → redirect
  # Two leave-unit paths:
  #   1) MODEL leaves  → Still the unit (redirect)
  #   2) USER leaves   → Actually drop that… (amend; no redirect)
  #
  # ── How to run ───────────────────────────────────────────────
  # Live (Composer 2.5 — needs cursor-sdk + CURSOR_API_KEY):
  #   python3 examples/run_stay_on_unit_live.py
  #   → prints WHO / CHAT / PRODUCT / WHY lanes; writes live-run-log.json
  #
  # Offline (no model — default gate):
  #   python3 -m pytest -q
  #   python3 examples/verify_live_story.py
  #
  # Optional: pytest -m live  → shells out to the live runner
  # ─────────────────────────────────────────────────────────────


  Rule: Live model — build add(a, b), then sidetrack to a homepage

    Scenario: On-unit reply is quiet; homepage reply redirects once
      Given a fresh Composer 2.5 chat from examples/run_stay_on_unit_live.py

      When turn 1 builds add(a, b) in examples/live_fixture/add.py
      And the check add(2, 3) == 5 exits 0
      Then the on-unit product follow-up is empty

      When turn 2 writes examples/live_fixture/HOMEPAGE.md
      And the assistant describes only that marketing page
      Then one short followup is "Still the unit: … add(a, b)…"
      And the followup does not say "no drift"
      And the unit string is still the add unit


  Rule: Offline fixture — same story without calling a model
  # Transcript: examples/fixtures/live_chat.json

    Scenario: Question records only
      Given the transcript in examples/fixtures/live_chat.json
      When the user asks why add() does not exist yet
      Then the product records only
      And stop stays empty

    Scenario: Naming the unit arms the pin
      Given the transcript in examples/fixtures/live_chat.json
      When the user sets Current unit to add(a, b) in examples/live_fixture/add.py
      Then the unit is armed
      And there is no chat message

    Scenario: Building on-unit stays quiet
      Given an open unit about add(a, b)
      When the agent writes add.py and the check passes
      Then stop stays empty
      And the pin still quotes add(a, b)

    Scenario: Homepage sidetrack redirects; unit string unchanged
      Given an open unit about add(a, b)
      When the agent describes a marketing homepage with a signup line
      Then one short followup is "Still the unit: … add(a, b)…"
      And the followup does not say "no drift"
      And the unit string is not replaced by homepage

    Scenario: User amends the unit; homepage work goes quiet
      Given an open unit about add(a, b)
      When the user says Actually drop that. Design the homepage instead
      Then the unit amends to the homepage
      And a later homepage reply stays quiet


  Rule: Limit cases

    Scenario: Non-homepage sidetrack still redirects
      Given an open unit about add(a, b)
      When the assistant says it wrote a database migration for the billing schema instead
      Then context-guard posts Still the unit

    Scenario: Claiming you stayed on the unit does not redirect
      Given an open unit about add(a, b)
      When the assistant says it did not write a marketing page
      And the open unit is still the add function
      Then stop stays empty
