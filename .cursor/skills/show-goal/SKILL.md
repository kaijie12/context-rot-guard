---
name: show-goal
description: >-
  Print the living context goal for this chat: the named goal, the check, and
  later requirements. Use when the user asks for the goal, the context goal,
  goal show, what the chat is held to, or a summary of the current goal.
  If there is no goal yet and the user wants one recovered from chat history,
  run goal recover.
---

# Show the context goal

Print the goal context-guard is holding. Do not write your own summary of the chat.

From the repo root:

```bash
python3 -m context_guard goal show
```

Paste that stdout to the user unchanged. Fresh goals are a sentence, optional `Check:`, and `-` Held lines. After recover, expect Arc / Held now / Rejected / cancelled / Open. `No goal.` means nothing is stored for the default conversation.

If that prints `No goal.` and `.context-guard/chats/` has other files, run the same command with `--conversation` set to the filename stem of the newest file, and say which conversation that was. If the user names a conversation, use that id instead.

If `goal show` is still `No goal.` and the user asked to recover the goal, or to show the goal for a long existing chat that never named one, run:

```bash
python3 -m context_guard goal recover --conversation <id>
```

Paste that stdout. See the README Day to day section. A goal is also armed by `/goal …` or `Current goal: …` in chat, or by `goal start`. Cursor's CreateGoal tool alone does not fill this store.
