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

  Rule: The loop is a check a program can fail

    Scenario: No check has been recorded
      Given the open goal includes the exempt-invoice check
      And no check result is recorded
      When the assistant reply is still about that invoice goal
      Then context-guard posts one correction that the check is still open
      And the correction quotes the living goal
      And the correction tells the model to stay on that goal
      # "Looks done", model confidence, and "no exception" are not checks.

    Scenario: The check is red once
      Given the open goal includes the exempt-invoice check
      And the check ran once and exited non-zero
      When the assistant reply is still about that invoice goal
      Then context-guard posts one correction that quotes the failing result
      And the correction tells the model to stay on that goal

    Scenario: The same failure repeats
      Given the open goal includes the exempt-invoice check
      And the same failing check output has been recorded twice
      When the assistant reply is still about that invoice goal
      Then context-guard posts "Stop and replan. Goal still:"
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
