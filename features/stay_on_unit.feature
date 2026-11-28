Feature: Living goal and the check loop
  As a developer who adds rules after the goal is named
  I want those rules kept on a goal I can open at any time
  And I want a check, not the model's confidence, to decide when the work is finished
  So a late rule is not lost and a stopped-short run is not treated as done

  # Spec: the problem statement. User lines below are the user's words.
  # Assistant text is not invented. The off-goal case names a judge verdict.
  # A real subagent run comes after the offline suite is green.
  #
  # Goal: exempt customers pay no tax.
  # Check: an exempt customer with a $100 subtotal totals $100, command exits 0.
  # Late details: a reseller certificate exempts only the home state;
  # a marketplace order is never exempt.

  Rule: The living goal collects requirements and stays visible

    Scenario: Name the goal and the check
      Given no goal is open
      When the user names the exempt-invoice goal and the check that must exit 0
      Then goal show prints that goal and that check
      And context-guard posts no chat message

    Scenario: A later detail is added to the goal
      Given the open goal is the exempt-invoice fix
      When the user adds that a reseller certificate exempts only the home state
      And the user adds that a marketplace order is never exempt
      Then goal show still shows the exempt-invoice goal
      And goal show lists the home-state rule
      And goal show lists the marketplace rule
      And context-guard posts no chat message

    Scenario: A question is not a new requirement
      Given the open goal lists the home-state rule and the marketplace rule
      When the user asks whether anything else in the folder would mislead someone about tax
      Then the goal text is unchanged
      And context-guard does not post "Still the goal"

    Scenario: Drop a detail
      Given the open goal lists the marketplace rule
      When the user says Actually drop that. The marketplace rule no longer applies
      Then goal show no longer lists the marketplace rule
      And context-guard posts no chat message

  Rule: Without /goal-loop, on-track stops stay silent

    Scenario: No check has been recorded
      Given the open goal includes the exempt-invoice check
      And no check result is recorded
      When the assistant reply is still about that invoice goal
      Then context-guard stays silent
      # Optional Check is not the stop loop. Use /goal-loop for Open items.

    Scenario: The check is red once
      Given the open goal includes the exempt-invoice check
      And the check ran once and exited non-zero
      When the assistant reply is still about that invoice goal
      Then context-guard stays silent

    Scenario: The same failure repeats
      Given the open goal includes the exempt-invoice check
      And the same failing check output has been recorded twice
      When the assistant reply is still about that invoice goal
      Then context-guard stays silent
      And the living goal is unchanged

    Scenario: The check passes
      Given the open goal includes the exempt-invoice check
      And the check exited 0
      When the assistant reply is still about that invoice goal
      Then context-guard stays silent

  Rule: Other work is a judge verdict, not an invented reply

    Scenario: The judge says the reply is other work
      Given the open goal lists the home-state rule and the marketplace rule
      When the judge verdict on the assistant reply is off_goal
      Then context-guard posts one "Still the goal" line
      And that line includes the home-state rule and the marketplace rule
      And the stored goal is unchanged

    # Acceptance: examples/run_stay_on_unit_live.py (Composer 2.5, Fast off,
    # CursorModelJudge). Offline pytest does not call the model for this scenario.
    Scenario: A user steers the chat off the invoice and the live judge redirects
      Given the open goal lists the home-state rule and the marketplace rule
      When the user asks for a billing homepage blurb instead of the invoice fix
      And a live model replies to that ask
      Then the judge verdict is off_goal
      And context-guard posts one "Still the goal" line
      And that line includes the home-state rule and the marketplace rule
      And the stored goal is unchanged
