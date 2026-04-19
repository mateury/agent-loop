"""Abstract base for messenger bridges."""

from __future__ import annotations

from abc import ABC, abstractmethod


class MessengerBridge(ABC):
    """Interface every messenger bridge must implement.

    A bridge handles platform-specific concerns: receiving messages, formatting
    output, sending files, showing typing indicators. It does NOT know about
    Claude, sessions, or memory — those are the controller's responsibility.
    """

    @abstractmethod
    async def start(self) -> None:
        """Start the bridge (connect to API, set up webhooks, etc.)."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully shut down the bridge."""
        ...

    @abstractmethod
    async def send_message(self, chat_id: str, text: str) -> None:
        """Send a formatted text message to a chat."""
        ...

    @abstractmethod
    async def send_progress(self, chat_id: str, text: str) -> None:
        """Send a short progress/status update (e.g., tool use description)."""
        ...

    @abstractmethod
    async def send_typing(self, chat_id: str) -> None:
        """Show typing indicator in a chat."""
        ...

    @abstractmethod
    async def send_file(self, chat_id: str, path: str, caption: str = "") -> None:
        """Send a file (auto-detect type: photo, video, document)."""
        ...

    @abstractmethod
    async def notify(self, text: str) -> None:
        """Send a proactive notification to the default chat."""
        ...
