"""Telegram messenger bridge."""

from agent_loop.bridges import register_bridge
from agent_loop.bridges.telegram.bot import TelegramBridge

register_bridge("telegram", TelegramBridge)

__all__ = ["TelegramBridge"]
