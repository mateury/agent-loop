"""Heartbeat loop — autonomous action every N minutes.

Picks and executes the single highest-value action. Uses persistent sessions
for continuity within a day.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime
from pathlib import Path

from agent_loop.config import Config
from agent_loop.core.claude import run_claude_text
from agent_loop.util.pidlock import PidLock

log = logging.getLogger(__name__)

INIT_PROMPT_TEMPLATE = """\
You are an autonomous heartbeat agent running every {interval} minutes \
({active_start}:00–{active_end}:00). This is a PERSISTENT SESSION — you \
remember previous heartbeats within today.

Your job: PICK and EXECUTE the single most valuable action each time you're called.

Rules:
- Execute ONE action per heartbeat, completable in under {timeout_min} minutes
- After executing, update the todo file if you completed a task
- Do NOT modify memory files directly
- Do NOT modify session-context — READ ONLY
- If nothing valuable to do — skip, report all clear
- Do NOT repeat actions you already did in this session
- Language: {language}

Steps each beat:
1. Read the todo file for pending tasks
2. Read session-context for recent context
3. Review system health (provided below)
4. Pick the highest-value action considering priority and impact

Output format:
**Heartbeat — {timestamp}**
**Did:** [one sentence describing what you did]
**Why:** [one sentence why this was the top priority]
**System:** [only if something needs attention, skip if all OK]
"""

STATE_PROMPT_TEMPLATE = """\

--- Current state ({timestamp}) ---
Open tasks: {open_tasks} (urgent: {urgent_tasks})

System health:
{system_health}

Execute heartbeat.
"""


def _get_state_hash(config: Config) -> str:
    """Hash todo + session-context for file-change detection."""
    content = ""
    todo_path = config.project_root / "data" / "todo.md"
    ctx_path = config.project_root / "data" / "session-context.md"
    for path in (todo_path, ctx_path):
        if path.exists():
            content += path.read_text()
    return hashlib.md5(content.encode()).hexdigest()


def _count_tasks(config: Config) -> tuple[int, int]:
    """Count open tasks and urgent (red) tasks."""
    todo_path = config.project_root / "data" / "todo.md"
    if not todo_path.exists():
        return 0, 0

    content = todo_path.read_text()
    open_tasks = content.count("- [ ]")
    urgent = sum(1 for line in content.split("\n") if "- [ ]" in line and "\U0001f534" in line)
    return open_tasks, urgent


async def run_heartbeat(config: Config) -> str | None:
    """Execute one heartbeat cycle.

    Returns:
        Output text if action was taken, None if skipped.
    """
    hb = config.loops.heartbeat
    state_dir = Path("/tmp/agent-loop-heartbeat")
    state_dir.mkdir(parents=True, exist_ok=True)

    # PID lock
    lock = PidLock(state_dir / "heartbeat.pid")
    if not lock.acquire():
        log.info("Heartbeat already running, skipping")
        return None

    try:
        return await _execute_heartbeat(config, hb, state_dir)
    finally:
        lock.release()


async def _execute_heartbeat(config, hb, state_dir: Path) -> str | None:
    session_file = state_dir / "session-id"
    hash_file = state_dir / "last-hash"
    log_file = config.project_root / config.logging.log_dir / "heartbeat.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Check if state changed (optional trigger)
    current_hash = _get_state_hash(config)
    if hash_file.exists():
        old_hash = hash_file.read_text().strip()
        if current_hash == old_hash:
            log.debug("No state change detected")
    hash_file.write_text(current_hash)

    # Session management
    is_new = False
    if session_file.exists():
        session_id = session_file.read_text().strip()
    else:
        session_id = str(uuid.uuid4())
        session_file.write_text(session_id)
        is_new = True

    timestamp = datetime.now().strftime("%H:%M")
    open_tasks, urgent_tasks = _count_tasks(config)

    # Build prompt
    state_prompt = STATE_PROMPT_TEMPLATE.format(
        timestamp=timestamp,
        open_tasks=open_tasks,
        urgent_tasks=urgent_tasks,
        system_health="(no health check configured)",
    )

    if is_new:
        init_prompt = INIT_PROMPT_TEMPLATE.format(
            interval=hb.interval_minutes,
            active_start=hb.active_hours_start,
            active_end=hb.active_hours_end,
            timeout_min=hb.timeout // 60,
            language=config.agent.language,
            timestamp=timestamp,
        )
        full_prompt = init_prompt + state_prompt
    else:
        full_prompt = state_prompt

    # Execute
    if is_new:
        output, exit_code = await run_claude_text(
            prompt=full_prompt,
            claude_path=config.claude_path,
            new_session_id=session_id,
            model=hb.model,
            timeout=hb.timeout,
        )
    else:
        output, exit_code = await run_claude_text(
            prompt=full_prompt,
            claude_path=config.claude_path,
            session_id=session_id,
            model=hb.model,
            timeout=hb.timeout,
        )

        # Fallback: if resume failed, start new session
        if exit_code != 0:
            log.warning("Resume failed (exit %d), creating new session", exit_code)
            session_id = str(uuid.uuid4())
            session_file.write_text(session_id)
            init_prompt = INIT_PROMPT_TEMPLATE.format(
                interval=hb.interval_minutes,
                active_start=hb.active_hours_start,
                active_end=hb.active_hours_end,
                timeout_min=hb.timeout // 60,
                language=config.agent.language,
                timestamp=timestamp,
            )
            output, exit_code = await run_claude_text(
                prompt=init_prompt + state_prompt,
                claude_path=config.claude_path,
                new_session_id=session_id,
                model=hb.model,
                timeout=hb.timeout,
            )

    # Log
    with open(log_file, "a") as f:
        f.write(f"=== {datetime.now():%Y-%m-%d %H:%M} === exit: {exit_code} ===\n")
        f.write(output + "\n")

    if exit_code == 0 and output:
        return output
    return None
