"""Session management — tracks Claude sessions per chat, supports resume/reset."""

from __future__ import annotations

import logging
import uuid

log = logging.getLogger(__name__)


class SessionManager:
    """Manages Claude Code session IDs per chat.

    Each chat (user or group) can have one active session. The session ID is
    passed to Claude via --resume to maintain conversation continuity.
    """

    def __init__(self):
        self._sessions: dict[str, str] = {}  # chat_id (str) -> session_id

    def get(self, chat_id: str | int) -> str | None:
        """Get the current session ID for a chat, or None if no active session."""
        return self._sessions.get(str(chat_id))

    def set(self, chat_id: str | int, session_id: str):
        """Set (or update) the session ID for a chat."""
        self._sessions[str(chat_id)] = session_id
        log.info("Session updated for chat %s: %s", chat_id, session_id[:8])

    def reset(self, chat_id: str | int) -> str | None:
        """Clear the session for a chat. Returns the old session ID."""
        old = self._sessions.pop(str(chat_id), None)
        if old:
            log.info("Session reset for chat %s (was %s)", chat_id, old[:8])
        return old

    def create(self, chat_id: str | int | None = None) -> str:
        """Create a new session ID. Optionally associate it with a chat."""
        session_id = str(uuid.uuid4())
        if chat_id is not None:
            self._sessions[str(chat_id)] = session_id
        return session_id

    @property
    def active_count(self) -> int:
        """Number of active sessions."""
        return len(self._sessions)

    def all_sessions(self) -> dict[str, str]:
        """Return a copy of all active sessions."""
        return dict(self._sessions)
