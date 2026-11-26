---
name: context-guard
description: >-
  Name the current goal of a large task so context-guard can pin it and
  redirect only if that goal is abandoned. Use before a bounded chunk of work,
  or when the user says current goal, next goal, mission, or follow the loop.
---

# Context guard goal

Hooks already record the chat. You do not turn the product on per message.

When the work is a large task, name one goal before coding that chunk:

```bash
python3 -m context_guard goal start \
  --goal "<one goal>" \
  --done-means "<what finished means>" \
  --mission "<durable ask, if not already set>"
```

Or say it in the chat: `/goal …` / `Current goal: …` / `Next goal: …`, and add a `Check: …` line. See the README "Day to day" section. `goal show` prints the living goal for that chat.

Questions and investigations do not lock a mission. A new file that serves the goal is not off-track. If you are told to drop the goal, wait for the user to amend it; do not invent a new mission.
