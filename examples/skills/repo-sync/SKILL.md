---
name: repo-sync
description: Pull latest changes across multiple git repos and report what changed
version: 1.0.0
platforms: [linux, macos]
tags: [git, maintenance, productivity]
metadata:
  agentskills:
    compatible: true
---

# Repo Sync

Pull the latest commits across a list of local git repositories and summarise what arrived. Good as a morning startup action.

## Steps

1. **Define repos** — list the directories to sync (edit to match your setup):
   ```bash
   REPOS=(
     /path/to/repo-one
     /path/to/repo-two
     /path/to/repo-three
   )
   ```

2. **Pull each repo** — skip if dirty (uncommitted changes):
   ```bash
   for repo in "${REPOS[@]}"; do
     if [ -d "$repo/.git" ]; then
       cd "$repo"
       if git diff --quiet && git diff --cached --quiet; then
         git pull --ff-only 2>&1
       else
         echo "SKIP $repo — uncommitted changes"
       fi
     fi
   done
   ```

3. **Collect new commits** — for each repo that updated, list what arrived:
   ```bash
   git log --oneline HEAD@{1}..HEAD
   ```

4. **Produce output** in this format:
   ```
   # Repo Sync — YYYY-MM-DD HH:MM

   ## Updated
   - repo-one: 3 new commits
     - abc1234 fix: handle timeout in worker
     - def5678 feat: add retry logic
     - ghi9012 chore: bump deps

   ## Already up to date
   - repo-two

   ## Skipped (dirty)
   - repo-three — 2 modified files
   ```

5. If any repo has merge conflicts or pull failures, flag them clearly and do NOT attempt auto-resolution.

## Notes

- Use `--ff-only` to avoid accidental merge commits
- Never force-push or reset; just report conflicts and let the user resolve
- This skill is read-heavy and safe to run on a schedule
