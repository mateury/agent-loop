"""Memory tier tracking — access counts, TTL, tier classification."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

TIERS = ("core", "standard", "ephemeral")


class MemoryStats:
    """Tracks memory file access patterns and tier assignments.

    Data stored in memory-stats.json:
    {
        "_meta": { "version": 1, ... },
        "files": {
            "filename.md": {
                "tier": "standard",
                "access_count": 4,
                "last_accessed": "2026-04-19"
            }
        }
    }
    """

    def __init__(self, stats_path: str | Path):
        self.path = Path(stats_path)
        self._data: dict = {"_meta": {"version": 1}, "files": {}}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text())
            except (json.JSONDecodeError, OSError) as e:
                log.warning("Failed to load memory stats: %s", e)

    def _save(self):
        """Atomic write — write to tmp, then move."""
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False))
        tmp_path.rename(self.path)

    def get_tier(self, filename: str) -> str:
        """Get the tier of a memory file (default: standard)."""
        entry = self._data.get("files", {}).get(filename, {})
        return entry.get("tier", "standard")

    def set_tier(self, filename: str, tier: str):
        """Set the tier of a memory file."""
        if tier not in TIERS:
            raise ValueError(f"Invalid tier: {tier}. Must be one of {TIERS}")
        files = self._data.setdefault("files", {})
        entry = files.setdefault(filename, {})
        entry["tier"] = tier
        self._save()

    def record_access(self, filename: str):
        """Record that a memory was accessed."""
        today = datetime.now().strftime("%Y-%m-%d")
        files = self._data.setdefault("files", {})
        entry = files.setdefault(filename, {"tier": "standard", "access_count": 0})
        entry["access_count"] = entry.get("access_count", 0) + 1
        entry["last_accessed"] = today
        self._save()

    def get_stats(self, filename: str) -> dict:
        """Get stats for a memory file."""
        return self._data.get("files", {}).get(filename, {})

    def all_stats(self) -> dict[str, dict]:
        """Get stats for all tracked files."""
        return dict(self._data.get("files", {}))

    def stale_files(self, days: int = 30) -> list[str]:
        """Find files not accessed in the last N days."""
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        stale = []
        for filename, entry in self._data.get("files", {}).items():
            last = entry.get("last_accessed", "")
            if last and last < cutoff:
                stale.append(filename)
        return stale

    def register_file(self, filename: str, tier: str = "standard"):
        """Register a new file in stats (if not already tracked)."""
        files = self._data.setdefault("files", {})
        if filename not in files:
            files[filename] = {
                "tier": tier,
                "access_count": 0,
                "last_accessed": datetime.now().strftime("%Y-%m-%d"),
            }
            self._save()

    def remove_file(self, filename: str):
        """Remove a file from stats tracking."""
        files = self._data.get("files", {})
        if filename in files:
            del files[filename]
            self._save()

    def summary(self) -> dict:
        """Get summary stats: count by tier, total files."""
        files = self._data.get("files", {})
        by_tier = {t: 0 for t in TIERS}
        for entry in files.values():
            tier = entry.get("tier", "standard")
            by_tier[tier] = by_tier.get(tier, 0) + 1
        return {
            "total": len(files),
            "by_tier": by_tier,
        }
