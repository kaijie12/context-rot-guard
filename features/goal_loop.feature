Feature: Optional goal loop
  As a developer who already named a goal
  I want a loop only when I ask for it
  So the chat keeps going through what is still open, or asks for a new plan, and stays quiet otherwise

  # Spec for /goal-loop. Offline pytest uses ScriptedPlanner and does not call a live model.
  # Unarmed chats stay silent on stop unless the judge says off_goal.
  #
  # Goal: exempt customers pay no tax.
  # Open: home-state reseller rule; marketplace orders are never exempt.

  Rule: The loop is off until the user asks

    Scenario: An unarmed stop does not run the open-list loop
      Given the open goal lists the home-state rule and the marketplace rule as open items
      And goal-loop is not armed
      When the assistant reply is still about that invoice goal
      Then context-guard does not post "Still open"
      And the planner is not called

    Scenario: The user arms the loop
      Given the open goal lists the home-state rule and the marketplace rule as open items
      When the user says /goal-loop
      Then goal-loop is armed
      And context-guard posts no chat message from arming

    Scenario: The user turns the loop off
      Given goal-loop is armed
      When the user says /goal-loop off
      Then goal-loop is not armed

  Rule: While armed, open items continue or a plan is requested

    Scenario: Open items get one continue line
      Given the open goal lists the home-state rule and the marketplace rule as open items
      And goal-loop is armed
      And the planner says the work can continue
      When the assistant reply is still about that invoice goal
      Then context-guard posts one "Still open" line
      And that line includes the home-state rule and the marketplace rule
      And goal-loop stays armed

    Scenario: A finished item leaves the open list
      Given the open goal lists the home-state rule and the marketplace rule as open items
      And goal-loop is armed
      And the planner marks the home-state rule done
      When the assistant reply is still about that invoice goal
      Then goal show no longer lists the home-state rule as open
      And goal show still lists the marketplace rule as open
      And the assistant reply alone did not clear the list

    Scenario: Nothing left open is silence
      Given the open goal lists the home-state rule as an open item
      And goal-loop is armed
      And the planner marks the home-state rule done
      When the assistant reply is still about that invoice goal
      Then context-guard stays silent
      And goal-loop is not armed

    Scenario: A named goal with no open list uses the goal sentence
      Given the open goal has no open items listed
      And goal-loop is armed
      And the planner says the work can continue
      When the assistant reply is still about that invoice goal
      Then context-guard posts one "Still open" line
      And that line includes the exempt-invoice goal

    Scenario: The next chunk needs a plan
      Given the open goal lists the home-state rule and the marketplace rule as open items
      And goal-loop is armed
      And the planner says this chunk needs a plan
      When the assistant reply is still about that invoice goal
      Then context-guard posts one line that asks for that plan
      And goal-loop is not armed

    Scenario: A failed planner does not invent a plan
      Given the open goal lists the home-state rule as an open item
      And goal-loop is armed
      And the planner call fails
      When the assistant reply is still about that invoice goal
      Then context-guard posts no "Still open" line and no plan
      And the home-state rule is still open

    Scenario: Leaving the goal still redirects once
      Given the open goal lists the home-state rule and the marketplace rule as open items
      And goal-loop is armed
      When the judge verdict on the assistant reply is off_goal
      Then context-guard posts one "Still the goal" line
      And the planner is not called

    Scenario: A passing check does not clear open items
      Given the open goal lists the home-state rule as an open item
      And the check exited 0
      And goal-loop is armed
      And the planner says the work can continue
      When the assistant reply is still about that invoice goal
      Then the home-state rule is still open
      And context-guard does not post "the check is still open"
