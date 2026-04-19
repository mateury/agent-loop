"""Memory maintenance — periodic cleanup, verification, enrichment."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from agent_loop.config import Config
from agent_loop.core.claude import run_claude_text
from agent_loop.util.pidlock import PidLock

log = logging.getLogger(__name__)

MAINTAIN_PROMPT_TEMPLATE = """\
You are a memory maintenance agent. Pick ONE action from the list below \
and execute it. Memory directory: {memory_dir}

Available actions (pick the most needed):
A. Verify that file paths mentioned in memories still exist
B. Add/update tags in memory frontmatter
C. Report journal entries older than 14 days (candidates for archival) — REPORT ONLY
D. Find duplicate or overlapping memories — REPORT ONLY
E. Enrich MEMORY.md descriptions (make hook-lines more specific)
F. Reorganize MEMORY.md sections (logical ordering)
G. Review memory-stats.json tiers (core/standard/ephemeral)
H. Check for stale memories (>30 days without access)

CRITICAL RULES:
- NEVER delete or merge memory files — only REPORT candidates
- Write to /tmp/ first, then move (atomic writes)
- Pick ONE action, execute it, report what you did

Language: {language}

Output format:
**Memory Maintenance — {timestamp}**
**Action:** [letter + description]
**Result:** [what you did/found]
"""


async def run_maintain(config: Config) -> str | None:
    """Execute one memory maintenance cycle.

    Returns:
        Summary text if action taken, None if skipped.
    """
    lock = PidLock(Path("/tmp/agent-loop-maintain.pid"))
    if not lock.acquire():
        log.info("Maintenance already running, skipping")
        return None

    try:
        return await _execute_maintain(config)
    finally:
        lock.release()


async def _execute_maintain(config: Config) -> str | None:
    memory_dir = config.project_root / config.memory.path
    timestamp = datetime.now().strftime("%H:%M")

    prompt = MAINTAIN_PROMPT_TEMPLATE.format(
        memory_dir=memory_dir,
        language=config.agent.language,
        timestamp=timestamp,
    )

    output, exit_code = await run_claude_text(
        prompt=prompt,
        claude_path=config.claude_path,
        model=config.loops.maintain.model,
        timeout=900,
    )

    # Log
    maintain_log = config.project_root / config.logging.log_dir / "memory-maintain.log"
    maintain_log.parent.mkdir(parents=True, exist_ok=True)
    with open(maintain_log, "a") as f:
        f.write(f"=== {datetime.now():%Y-%m-%d %H:%M} === exit: {exit_code} ===\n")
        f.write(output + "\n")

    if exit_code == 0 and output:
        return output
    return None
