"""Unit tests for agent_loop.core.nudges."""

import pytest
from agent_loop.core.nudges import NudgeCounters, MEMORY_NUDGE_TEXT, SKILL_NUDGE_TEXT


class TestNudgeCounters:
    def test_initial_state(self):
        nc = NudgeCounters()
        assert nc.turns_since_memory == 0
        assert nc.iters_since_skill == 0
        assert nc.memory_interval == 10
        assert nc.skill_interval == 15

    def test_custom_intervals(self):
        nc = NudgeCounters(memory_interval=5, skill_interval=8)
        assert nc.memory_interval == 5
        assert nc.skill_interval == 8

    def test_tick_turn_returns_none_before_interval(self):
        nc = NudgeCounters()
        for _ in range(9):
            assert nc.tick_turn() is None

    def test_tick_turn_returns_nudge_at_interval(self):
        nc = NudgeCounters()
        result = None
        for _ in range(10):
            result = nc.tick_turn()
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    def test_tick_turn_resets_counter_after_nudge(self):
        nc = NudgeCounters()
        for _ in range(10):
            nc.tick_turn()
        # counter should reset
        assert nc.turns_since_memory == 0

    def test_tick_turn_nudge_contains_turn_count(self):
        nc = NudgeCounters()
        for _ in range(10):
            result = nc.tick_turn()
        # nudge should reference the count
        assert "10" in result

    def test_tick_iter_returns_none_before_interval(self):
        nc = NudgeCounters()
        for _ in range(14):
            assert nc.tick_iter() is None

    def test_tick_iter_returns_nudge_at_interval(self):
        nc = NudgeCounters()
        result = None
        for _ in range(15):
            result = nc.tick_iter()
        assert result is not None
        assert "15" in result

    def test_tick_iter_resets_counter_after_nudge(self):
        nc = NudgeCounters()
        for _ in range(15):
            nc.tick_iter()
        assert nc.iters_since_skill == 0

    def test_reset_clears_all_counters(self):
        nc = NudgeCounters()
        for _ in range(5):
            nc.tick_turn()
            nc.tick_iter()
        nc.reset()
        assert nc.turns_since_memory == 0
        assert nc.iters_since_skill == 0

    def test_nudge_fires_again_after_reset(self):
        nc = NudgeCounters(memory_interval=3)
        for _ in range(3):
            nc.tick_turn()
        nc.reset()
        result = None
        for _ in range(3):
            result = nc.tick_turn()
        assert result is not None

    def test_independent_counters(self):
        nc = NudgeCounters(memory_interval=5, skill_interval=5)
        # Advance only turn counter
        for _ in range(5):
            nc.tick_turn()
        # iter counter should still be 0
        assert nc.iters_since_skill == 0
