"""Nudge counters — periodic reminders to persist knowledge.

Adopted from Hermes Agent: every N turns, inject a small reminder into
the user message encouraging the agent to consolidate learnings into memory.
Cheap way to make the agent proactive about long-term state.
"""

from __future__ import annotations

from dataclasses import dataclass


MEMORY_NUDGE_TEXT = (
    "[system reminder] This is turn #{turn_count}. If anything from recent "
    "conversation is worth persisting (new user preferences, project decisions, "
    "feedback patterns, or surprising insights), consider creating or updating "
    "a memory file now. Skip if nothing is worth saving."
)

SKILL_NUDGE_TEXT = (
    "[system reminder] You've been working on this task for {iter_count} "
    "iterations. If you've developed a repeatable workflow or procedure, "
    "consider saving it as a skill. Skip if not applicable."
)


@dataclass
class NudgeCounters:
    """Tracks turns/iterations to trigger periodic nudges."""

    turns_since_memory: int = 0
    iters_since_skill: int = 0
    memory_interval: int = 10
    skill_interval: int = 15

    def tick_turn(self) -> str | None:
        """Increment turn counter, return nudge text if due."""
        self.turns_since_memory += 1
        if self.turns_since_memory >= self.memory_interval:
            nudge = MEMORY_NUDGE_TEXT.format(turn_count=self.turns_since_memory)
            self.turns_since_memory = 0
            return nudge
        return None

    def tick_iter(self) -> str | None:
        """Increment iteration counter, return nudge text if due."""
        self.iters_since_skill += 1
        if self.iters_since_skill >= self.skill_interval:
            nudge = SKILL_NUDGE_TEXT.format(iter_count=self.iters_since_skill)
            self.iters_since_skill = 0
            return nudge
        return None

    def reset(self):
        """Reset all counters (e.g., on /new session)."""
        self.turns_since_memory = 0
        self.iters_since_skill = 0
