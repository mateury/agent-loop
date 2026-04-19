"""Daily digest — journal entry + memory insight extraction."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from agent_loop.config import Config
from agent_loop.core.claude import run_claude_text
from agent_loop.util.pidlock import PidLock

log = logging.getLogger(__name__)

DIGEST_PROMPT_TEMPLATE = """\
You are a daily digest agent. Today is {today}. Your job:

1. Read the conversation log at {log_path} (today's entries)
2. Create a journal entry at {journal_path} with this format:
   ---
   name: Journal {today}
   description: Daily summary for {today}
   type: journal
   ---
   ## Summary
   ### What was done
   ### Key decisions
   ### In progress / for tomorrow

3. Extract any NEW insights from today's conversations:
   - New user preferences → create/update user memory
   - New project knowledge → create/update project memory
   - New feedback/corrections → create/update feedback memory
   Only create memories for things that are NOT already captured.

4. Update MEMORY.md index with the journal entry (add to ## Journal section)
   Keep max 7 journal entries in the index.

Memory directory: {memory_dir}
Language: {language}

Output a short summary of what you did (1-3 sentences).
"""


async def run_digest(config: Config) -> str | None:
    """Execute daily digest — create journal + extract insights.

    Returns:
        Summary text if successful, None if skipped.
    """
    lock = PidLock(Path("/tmp/agent-loop-digest.pid"))
    if not lock.acquire():
        log.info("Digest already running, skipping")
        return None

    try:
        return await _execute_digest(config)
    finally:
        lock.release()


async def _execute_digest(config: Config) -> str | None:
    today = datetime.now().strftime("%Y-%m-%d")
    log_path = config.project_root / config.logging.log_dir / "conversation.log"
    memory_dir = config.project_root / config.memory.path
    journal_path = memory_dir / f"journal_{today}.md"

    if not log_path.exists():
        log.info("No conversation log found, skipping digest")
        return None

    prompt = DIGEST_PROMPT_TEMPLATE.format(
        today=today,
        log_path=log_path,
        journal_path=journal_path,
        memory_dir=memory_dir,
        language=config.agent.language,
    )

    output, exit_code = await run_claude_text(
        prompt=prompt,
        claude_path=config.claude_path,
        model=config.loops.digest.model,
        timeout=600,
    )

    # Log
    digest_log = config.project_root / config.logging.log_dir / "daily-digest.log"
    digest_log.parent.mkdir(parents=True, exist_ok=True)
    with open(digest_log, "a") as f:
        f.write(f"=== {today} === exit: {exit_code} ===\n")
        f.write(output + "\n")

    if exit_code == 0 and output:
        return f"**Daily Digest** ({today})\n{output}"
    return None
