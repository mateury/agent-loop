"""Agent controller — orchestrates Claude runner, sessions, and bridge.

Handles concurrency: main session lock + side session semaphore.
Bridge-agnostic — receives messages from bridge, sends responses back via callbacks.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Awaitable

from agent_loop.config import Config
from agent_loop.core.claude import (
    ClaudeEvent,
    ProgressEvent,
    ResultEvent,
    run_claude_stream,
)
from agent_loop.core.nudges import NudgeCounters
from agent_loop.core.session import SessionManager
from agent_loop.memory.fencing import (
    inject_into_prompt,
    sanitize_user_input,
    wrap_memory_context,
)
from agent_loop.search import SessionStore
from agent_loop.util.logging import log_usage, log_conversation

log = logging.getLogger(__name__)


@dataclass
class Response:
    """Result of processing a user message."""

    text: str
    session_id: str
    is_error: bool = False
    is_side_session: bool = False


class AgentController:
    """Core agent logic — manages Claude sessions and message processing.

    The controller is bridge-agnostic. The bridge calls `handle_message()` and
    provides callbacks for sending progress/typing/responses.
    """

    def __init__(self, config: Config):
        self.config = config
        self.sessions = SessionManager()
        self.model: str | None = config.agent.model
        self._lock = asyncio.Lock()  # protects main session (--resume)
        self._semaphore = asyncio.Semaphore(config.bridge.max_side_sessions)
        self._last_usage: dict | None = None
        self._last_rate_limit: dict | None = None

        # FTS5 session store for cross-session recall
        db_path = config.project_root / "data" / "sessions.db"
        self.store = SessionStore(db_path)

        # Nudge counters (per chat — each chat has its own cadence)
        self._nudges: dict[str, NudgeCounters] = {}

    async def handle_message(
        self,
        chat_id: str,
        text: str,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        on_typing: Callable[[], Awaitable[None]] | None = None,
    ) -> Response:
        """Process a user message through Claude.

        Tries main session (with lock). If busy, spawns a side session.

        Args:
            chat_id: Chat identifier.
            text: User message text.
            on_progress: Callback for progress updates (e.g., "[1] Reading file: bot.py").
            on_typing: Callback for typing indicator.

        Returns:
            Response with Claude's output.
        """
        # Sanitize and log the raw user message
        text = sanitize_user_input(text)
        self._log_conversation(text, "user")

        # Enrich prompt with memory context + cross-session recall + nudge
        enriched = self._enrich_prompt(chat_id, text)

        # Try main session (non-blocking)
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=0.1)
        except asyncio.TimeoutError:
            log.info("Main session busy — spawning side session")
            return await self._run_side_session(chat_id, enriched, on_progress, on_typing)

        try:
            return await self._run_main_session(
                chat_id, enriched, on_progress, on_typing, original_text=text
            )
        finally:
            self._lock.release()

    async def _run_main_session(
        self,
        chat_id: str,
        text: str,
        on_progress: Callable[[str], Awaitable[None]] | None,
        on_typing: Callable[[], Awaitable[None]] | None,
        original_text: str | None = None,
    ) -> Response:
        """Run in main session with --resume for continuity.

        Args:
            text: Enriched prompt (with memory fencing + recall + nudge).
            original_text: Raw user input — what we persist to search/history.
        """
        session_id = self.sessions.get(chat_id)
        persist_text = original_text if original_text is not None else text

        result = await self._execute_claude(
            text,
            session_id=session_id,
            on_progress=on_progress,
            on_typing=on_typing,
        )

        if result.session_id:
            self.sessions.set(chat_id, result.session_id)
            # Persist RAW user input (not enriched) so search indexes actual user turns
            self.store.start_session(result.session_id, chat_id, self.model)
            self.store.add_message(result.session_id, "user", persist_text)
            self.store.add_message(result.session_id, "assistant", result.text)

        self._log_conversation(result.text, "assistant")
        return result

    async def _run_side_session(
        self,
        chat_id: str,
        text: str,
        on_progress: Callable[[str], Awaitable[None]] | None,
        on_typing: Callable[[], Awaitable[None]] | None,
    ) -> Response:
        """Run a parallel side session (no --resume)."""
        async with self._semaphore:
            result = await self._execute_claude(
                text,
                session_id=None,
                on_progress=on_progress,
                on_typing=on_typing,
            )
            result.is_side_session = True
            self._log_conversation(result.text, "assistant")
            return result

    async def _execute_claude(
        self,
        prompt: str,
        session_id: str | None,
        on_progress: Callable[[str], Awaitable[None]] | None,
        on_typing: Callable[[], Awaitable[None]] | None,
    ) -> Response:
        """Execute Claude CLI and collect the result."""
        typing_task = None
        if on_typing:
            typing_task = asyncio.create_task(self._keep_typing(on_typing))

        result_text = ""
        result_session_id = ""
        is_error = False

        try:
            async for event in run_claude_stream(
                prompt=prompt,
                claude_path=self.config.claude_path,
                session_id=session_id,
                model=self.model,
                timeout=self.config.agent.timeout,
                progress_interval=self.config.bridge.progress_interval,
            ):
                if isinstance(event, ProgressEvent) and on_progress:
                    try:
                        await on_progress(event.text)
                    except Exception as e:
                        log.warning("Failed to send progress: %s", e)

                elif isinstance(event, ResultEvent):
                    result_text = event.text
                    result_session_id = event.session_id
                    is_error = event.is_error
                    self._last_usage = event.usage

                    # Log usage to CSV
                    if self.config.logging.usage_csv and event.usage:
                        usage_csv = (
                            self.config.project_root
                            / self.config.logging.log_dir
                            / "usage.csv"
                        )
                        log_usage(event.usage, self.model, usage_csv)

        except Exception as e:
            result_text = f"Error: {e}"
            is_error = True
        finally:
            if typing_task:
                typing_task.cancel()
                try:
                    await typing_task
                except asyncio.CancelledError:
                    pass

        if not result_text:
            result_text = "No response from Claude"
            is_error = True

        return Response(
            text=result_text,
            session_id=result_session_id,
            is_error=is_error,
        )

    async def _keep_typing(self, on_typing: Callable[[], Awaitable[None]]):
        """Continuously send typing indicator."""
        try:
            while True:
                await on_typing()
                await asyncio.sleep(self.config.bridge.typing_interval)
        except asyncio.CancelledError:
            pass

    def set_model(self, model: str | None):
        """Change the current model."""
        self.model = model
        log.info("Model changed to: %s", model)

    def reset_session(self, chat_id: str) -> str | None:
        """Reset a chat's session."""
        self._nudges.pop(chat_id, None)
        return self.sessions.reset(chat_id)

    def _get_nudges(self, chat_id: str) -> NudgeCounters:
        """Get (or create) nudge counters for a chat."""
        if chat_id not in self._nudges:
            self._nudges[chat_id] = NudgeCounters()
        return self._nudges[chat_id]

    def _enrich_prompt(self, chat_id: str, user_text: str) -> str:
        """Enrich a user prompt with memory context, cross-session recall, and nudges.

        - Looks up recent memory index
        - Searches past sessions for relevant hits (bypasses if memory disabled)
        - Optionally appends a nudge reminder every N turns
        """
        if not self.config.memory.enabled:
            return user_text

        # Load memory index (if present)
        memory_index_path = (
            self.config.project_root / self.config.memory.path / "MEMORY.md"
        )
        memory_text = ""
        if memory_index_path.exists():
            try:
                memory_text = memory_index_path.read_text()
            except OSError:
                pass

        # Search past sessions (exclude current one to avoid redundancy)
        current_sid = self.sessions.get(chat_id)
        hits: list[dict] = []
        try:
            hits = self.store.search(
                user_text, limit=5, exclude_session=current_sid
            )
        except Exception as e:
            log.warning("Session search failed: %s", e)

        # Build fenced memory block
        memory_block = wrap_memory_context(memory_text, hits)

        # Tick nudge counter, append reminder if due
        nudges = self._get_nudges(chat_id)
        nudge_text = nudges.tick_turn()

        # Assemble final prompt
        enriched = inject_into_prompt(user_text, memory_block)
        if nudge_text:
            enriched = f"{enriched}\n\n{nudge_text}"

        return enriched

    @property
    def last_usage(self) -> dict | None:
        return self._last_usage

    @property
    def last_rate_limit(self) -> dict | None:
        return self._last_rate_limit

    def _log_conversation(self, text: str, role: str):
        if not self.config.logging.conversation_log:
            return
        log_path = (
            self.config.project_root
            / self.config.logging.log_dir
            / "conversation.log"
        )
        log_conversation(text, role, log_path)
