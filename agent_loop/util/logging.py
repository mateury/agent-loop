"""Logging setup — structured logging + conversation log + usage CSV."""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

USAGE_FIELDS = [
    "timestamp",
    "model",
    "input_tokens",
    "output_tokens",
    "cache_read",
    "cache_create",
    "cost_usd",
    "num_turns",
    "duration_ms",
    "session_id",
]


def setup_logging(level: str = "INFO", log_dir: str | Path | None = None):
    """Configure root logger."""
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=getattr(logging, level.upper(), logging.INFO),
    )
    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)


def log_usage(usage_data: dict, model: str | None, log_path: Path):
    """Append token usage to a CSV file."""
    log = logging.getLogger(__name__)
    try:
        is_new = not log_path.exists()
        log_path.parent.mkdir(parents=True, exist_ok=True)

        usage = usage_data.get("usage", {})
        iterations = usage.get("iterations", [])
        last_iter = iterations[-1] if iterations else {}

        row = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "model": model or "unknown",
            "input_tokens": last_iter.get("input_tokens", 0),
            "output_tokens": last_iter.get("output_tokens", 0),
            "cache_read": last_iter.get("cache_read_input_tokens", 0),
            "cache_create": last_iter.get("cache_creation_input_tokens", 0),
            "cost_usd": usage_data.get("cost_usd", 0),
            "num_turns": usage_data.get("num_turns", 0),
            "duration_ms": usage_data.get("duration_ms", 0),
            "session_id": usage_data.get("session_id", ""),
        }

        with open(log_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=USAGE_FIELDS)
            if is_new:
                writer.writeheader()
            writer.writerow(row)
    except Exception as e:
        log.warning("Failed to log usage: %s", e)


def log_conversation(message: str, role: str, log_path: Path):
    """Append a conversation entry to the log file."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a") as f:
        # Escape newlines for single-line log entries
        clean = message.replace("\n", "\\n")[:500]
        f.write(f"{timestamp} [{role}] {clean}\n")
