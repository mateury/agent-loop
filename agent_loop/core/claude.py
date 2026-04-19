"""Claude Code CLI runner — async streaming bridge.

Runs `claude` CLI as a subprocess with stream-json output, yielding typed events.
This is bridge-agnostic — the caller (controller) decides what to do with events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator

from agent_loop.util.text import describe_tool_use

log = logging.getLogger(__name__)

# Available models — short name → full model ID
MODELS = {
    "opus": "claude-opus-4-7",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5-20251001",
}


# --- Event types emitted by the runner ---


@dataclass
class ToolUseEvent:
    """Claude is using a tool."""

    tool_count: int
    tool_name: str
    tool_input: dict
    description: str


@dataclass
class ProgressEvent:
    """Human-readable progress update (rate-limited)."""

    tool_count: int
    text: str


@dataclass
class RateLimitEvent:
    """Rate limit info from Claude API."""

    status: str
    resets_at: float
    rate_limit_type: str
    overage_status: str
    is_using_overage: bool
    timestamp: float


@dataclass
class ResultEvent:
    """Final result from Claude."""

    text: str
    session_id: str
    is_error: bool
    usage: dict = field(default_factory=dict)
    cost_usd: float = 0.0
    num_turns: int = 0
    duration_ms: int = 0


# Union of all events
ClaudeEvent = ToolUseEvent | ProgressEvent | RateLimitEvent | ResultEvent


def resolve_model(name: str | None) -> str | None:
    """Resolve a short model name to its full ID. Returns None if no override."""
    if not name:
        return None
    return MODELS.get(name, name)


async def run_claude_stream(
    prompt: str,
    claude_path: str = "claude",
    session_id: str | None = None,
    model: str | None = None,
    timeout: int = 600,
    progress_interval: float = 3.0,
    tool_labels: dict[str, str] | None = None,
) -> AsyncGenerator[ClaudeEvent, None]:
    """Run Claude CLI and yield typed events as they arrive.

    Args:
        prompt: The user prompt to send.
        claude_path: Path to claude CLI binary.
        session_id: Session ID to resume (--resume). None = new session.
        model: Model override (short name or full ID).
        timeout: Max seconds to wait for output.
        progress_interval: Min seconds between ProgressEvents.
        tool_labels: Custom tool name → label mapping.

    Yields:
        ClaudeEvent instances (ToolUseEvent, ProgressEvent, RateLimitEvent, ResultEvent).
    """
    cmd = [
        claude_path,
        "-p",
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--verbose",
    ]

    resolved_model = resolve_model(model)
    if resolved_model:
        cmd.extend(["--model", resolved_model])

    if session_id:
        cmd.extend(["--resume", session_id])

    cmd.append(prompt)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "NO_COLOR": "1"},
            limit=200 * 1024 * 1024,  # 200MB buffer for large stream-json lines
        )
    except Exception as e:
        yield ResultEvent(
            text=f"Failed to start Claude: {e}",
            session_id="",
            is_error=True,
        )
        return

    last_progress_time = 0.0
    tool_count = 0

    try:
        while True:
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                yield ResultEvent(
                    text="Timeout waiting for Claude response",
                    session_id="",
                    is_error=True,
                )
                return
            except ValueError as ve:
                log.warning("Oversized stream line skipped: %s", ve)
                try:
                    await asyncio.wait_for(proc.stdout.readline(), timeout=10)
                except Exception:
                    pass
                continue

            if not line:
                break

            raw = line.decode("utf-8", errors="replace").strip()
            if not raw:
                continue

            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                log.warning("Non-JSON line from stream: %s", raw[:100])
                continue

            event_type = event.get("type", "")

            if event_type == "assistant":
                message = event.get("message", {})
                for block in message.get("content", []):
                    if block.get("type") == "tool_use":
                        tool_count += 1
                        tool_name = block.get("name", "?")
                        tool_input = block.get("input", {})
                        desc = describe_tool_use(tool_name, tool_input, tool_labels)

                        yield ToolUseEvent(
                            tool_count=tool_count,
                            tool_name=tool_name,
                            tool_input=tool_input,
                            description=desc,
                        )

                        now = time.monotonic()
                        if now - last_progress_time >= progress_interval:
                            last_progress_time = now
                            yield ProgressEvent(
                                tool_count=tool_count,
                                text=f"[{tool_count}] {desc}",
                            )

            elif event_type == "rate_limit_event":
                info = event.get("rate_limit_info", {})
                if info:
                    yield RateLimitEvent(
                        status=info.get("status", "unknown"),
                        resets_at=info.get("resetsAt", 0),
                        rate_limit_type=info.get("rateLimitType", ""),
                        overage_status=info.get("overageStatus", ""),
                        is_using_overage=info.get("isUsingOverage", False),
                        timestamp=time.time(),
                    )

            elif event_type == "result":
                result_text = event.get("result", "")
                is_error = event.get("is_error", False)

                usage_data = {
                    "usage": event.get("usage", {}),
                    "model_usage": event.get("modelUsage", {}),
                    "cost_usd": event.get("total_cost_usd", 0),
                    "num_turns": event.get("num_turns", 0),
                    "duration_ms": event.get("duration_ms", 0),
                    "session_id": event.get("session_id", ""),
                }

                yield ResultEvent(
                    text=f"[Error] {result_text}" if is_error else result_text,
                    session_id=event.get("session_id", ""),
                    is_error=is_error,
                    usage=usage_data,
                    cost_usd=event.get("total_cost_usd", 0),
                    num_turns=event.get("num_turns", 0),
                    duration_ms=event.get("duration_ms", 0),
                )

    except Exception as e:
        yield ResultEvent(
            text=f"Streaming error: {e}",
            session_id="",
            is_error=True,
        )
    finally:
        if proc.returncode is None:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass

    # If we got no result event, check stderr
    if proc.returncode is not None and proc.returncode != 0:
        stderr = await proc.stderr.read()
        if stderr:
            yield ResultEvent(
                text=f"[stderr] {stderr.decode('utf-8', errors='replace').strip()}",
                session_id="",
                is_error=True,
            )


async def run_claude_text(
    prompt: str,
    claude_path: str = "claude",
    session_id: str | None = None,
    new_session_id: str | None = None,
    model: str | None = None,
    timeout: int = 600,
) -> tuple[str, int]:
    """Run Claude CLI with text output (non-streaming). Used by loops.

    Args:
        prompt: The prompt to send.
        claude_path: Path to claude CLI binary.
        session_id: Session ID to resume (--resume).
        new_session_id: Session ID for new session (--session-id).
        model: Model override.
        timeout: Max seconds.

    Returns:
        Tuple of (output_text, exit_code).
    """
    cmd = [
        claude_path,
        "-p",
        "--dangerously-skip-permissions",
        "--output-format",
        "text",
    ]

    resolved_model = resolve_model(model)
    if resolved_model:
        cmd.extend(["--model", resolved_model])

    if session_id:
        cmd.extend(["--resume", session_id])
    elif new_session_id:
        cmd.extend(["--session-id", new_session_id, "--name", "agent-loop"])

    cmd.append(prompt)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "NO_COLOR": "1"},
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode("utf-8", errors="replace").strip()
        if not output and stderr:
            output = stderr.decode("utf-8", errors="replace").strip()
        return output, proc.returncode or 0
    except asyncio.TimeoutError:
        proc.kill()
        return "Timeout waiting for Claude response", 1
    except Exception as e:
        return f"Failed to run Claude: {e}", 1
