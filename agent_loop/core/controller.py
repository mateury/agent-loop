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
from agent_loop.core.session import SessionManager
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
        # Log the user message
        self._log_conversation(text, "user")

        # Try main session (non-blocking)
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=0.1)
        except asyncio.TimeoutError:
            log.info("Main session busy — spawning side session")
            return await self._run_side_session(chat_id, text, on_progress, on_typing)

        try:
            return await self._run_main_session(
                chat_id, text, on_progress, on_typing
            )
        finally:
            self._lock.release()

    async def _run_main_session(
        self,
        chat_id: str,
        text: str,
        on_progress: Callable[[str], Awaitable[None]] | None,
        on_typing: Callable[[], Awaitable[None]] | None,
    ) -> Response:
        """Run in main session with --resume for continuity."""
        session_id = self.sessions.get(chat_id)

        result = await self._execute_claude(
            text,
            session_id=session_id,
            on_progress=on_progress,
            on_typing=on_typing,
        )

        if result.session_id:
            self.sessions.set(chat_id, result.session_id)

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
        return self.sessions.reset(chat_id)

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
