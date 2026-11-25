---
name: context-guard
description: >-
  Name the current unit of a large task so context-guard can pin it and
  redirect only if that unit is abandoned. Use before a bounded chunk of work,
  or when the user says current unit, next unit, or follow the loop.
---

# Context guard unit

Hooks already record the chat. You do not turn the product on per message.

When the work is a large task, name one unit before coding that chunk:

```bash
python3 -m context_guard unit start \
  --goal "<one unit>" \
  --done-means "<what finished means>" \
  --mission "<durable ask, if not already set>"
```

Or say it in the chat: `Current unit: …` / `Next unit: …` / `Mission: …`.

Questions and investigations do not lock a mission. A new file that serves the unit is not off-track. If you are told to drop the unit, wait for the user to amend it; do not invent a new mission.
