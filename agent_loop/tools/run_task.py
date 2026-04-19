"""Spawn a background Claude subagent for long-running tasks."""

from __future__ import annotations

import asyncio
import sys
import logging
from pathlib import Path

from agent_loop.config import load_config
from agent_loop.core.claude import run_claude_text
from agent_loop.util.pidlock import PidLock

log = logging.getLogger(__name__)


def main():
    """CLI: agent-run-task 'task name' ['prompt'] [model]"""
    if len(sys.argv) < 2:
        print("Usage: agent-run-task 'task name' ['prompt'] [model]", file=sys.stderr)
        sys.exit(1)

    task_name = sys.argv[1]
    prompt = sys.argv[2] if len(sys.argv) > 2 else task_name
    model = sys.argv[3] if len(sys.argv) > 3 else "sonnet"

    asyncio.run(_run(task_name, prompt, model))


async def _run(task_name: str, prompt: str, model: str):
    config = load_config()

    lock = PidLock(Path("/tmp/agent-loop-task.pid"))
    if not lock.acquire():
        print("Another task is already running", file=sys.stderr)
        sys.exit(1)

    try:
        log.info("Starting task: %s", task_name)

        # Notify start (best-effort)
        try:
            from agent_loop.tools.notify import _send
            await _send(f"Starting task: **{task_name}**")
        except Exception:
            pass

        output, exit_code = await run_claude_text(
            prompt=prompt,
            claude_path=config.claude_path,
            model=model,
            timeout=config.loops.heartbeat.timeout,
        )

        # Log
        log_path = config.project_root / config.logging.log_dir / "subagent.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            from datetime import datetime
            f.write(f"=== {datetime.now():%Y-%m-%d %H:%M} | {task_name} | exit: {exit_code} ===\n")
            f.write(output + "\n\n")

        # Notify result
        summary = output[-2000:] if len(output) > 2000 else output
        try:
            from agent_loop.tools.notify import _send
            status = "Completed" if exit_code == 0 else "Failed"
            await _send(f"**{status}:** {task_name}\n\n{summary}")
        except Exception:
            pass

        print(output)
    finally:
        lock.release()


if __name__ == "__main__":
    main()
