---
name: daily-review
description: Review today's work — commits, tasks completed, time spent
version: 1.0.0
platforms: [linux, macos]
tags: [productivity, review]
metadata:
  agentskills:
    compatible: true
---

# Daily Review

Conduct a thorough review of today's activities and produce a structured summary.

## Steps

1. **Check git activity** — list all commits across known repositories since midnight:
   ```bash
   git -C /path/to/repo log --oneline --since="today 00:00"
   ```

2. **Review the todo file** — identify tasks marked completed today (`[x]`) vs
   tasks still open (`[ ]`).

3. **Scan conversation log** (if present) for key decisions or blockers discussed.

4. **Produce output** in this format:
   ```
   # Daily Review — YYYY-MM-DD

   ## Shipped
   - <commit summary> (repo)

   ## Task progress
   - Completed: N tasks
   - Opened: N new
   - Remaining: N tasks

   ## Key decisions
   - <decision 1>

   ## Blockers / for tomorrow
   - <item 1>
   ```

5. Optionally, save the review as a journal entry in memory.
