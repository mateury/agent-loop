"""Messenger bridge registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_loop.bridges.base import MessengerBridge
    from agent_loop.config import Config

_REGISTRY: dict[str, type] = {}


def register_bridge(name: str, cls: type):
    """Register a messenger bridge class by name."""
    _REGISTRY[name] = cls


def get_bridge(name: str, config: "Config") -> "MessengerBridge":
    """Instantiate a registered bridge by name."""
    if name not in _REGISTRY:
        available = ", ".join(_REGISTRY.keys()) or "(none)"
        raise ValueError(f"Unknown bridge '{name}'. Available: {available}")
    return _REGISTRY[name](config)


def available_bridges() -> list[str]:
    """List registered bridge names."""
    return list(_REGISTRY.keys())
