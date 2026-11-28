---
name: goal-loop
description: >-
  Keep going through what is still open on the living goal, until nothing is
  left or a new plan is required. Use only when the user says /goal-loop,
  goal loop, keep going until the goal is done, or loop the open items.
  /goal-loop off stops it.
---

# Goal loop

This is off until the user asks. Do not arm it on your own.

A user message that is exactly `/goal-loop` arms this chat. `/goal-loop off` disarms it. While it is on, the stop followup either continues the open items or asks for a new plan. Do not invent a second continue line. When that followup requests a plan, stop looping until the user asks again.
