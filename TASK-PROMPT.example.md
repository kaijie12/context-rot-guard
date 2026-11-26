# Example closed-loop task prompt

Copy into an Agent chat when you want a change in this repo. This file is a template, not an open bug. The tree should already be green.

---

Change only what the task names in `context-guard`. Do not add an embedding client, a UI, or a second test runner.

**Closed loop (required):**

1. Keep going until this check is green:

   ```bash
   python3 -m pytest -q
   ```

2. Before claiming done, paste the **exact command** and the **last lines of output** (including the pass count).
3. If red: fix and re-run. Do not claim done without a green run.
4. Do not edit tests only to make the suite pass. If a test is wrong, say why and ask.

---

After the agent claims done: run the demo and expect a `DRIFT drift=true` line.

```bash
python3 examples/demo_drift_session.py
```
