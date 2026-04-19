"""PID file locking — prevents concurrent execution of the same process."""

from __future__ import annotations

import os
import signal
from pathlib import Path


class PidLock:
    """Context manager for PID-based exclusive locking."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _is_running(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def acquire(self) -> bool:
        """Try to acquire the lock. Returns True if acquired."""
        if self.path.exists():
            try:
                old_pid = int(self.path.read_text().strip())
                if self._is_running(old_pid):
                    return False
            except (ValueError, OSError):
                pass
            # Stale PID file — remove it
            self.path.unlink(missing_ok=True)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(str(os.getpid()))
        return True

    def release(self):
        """Release the lock."""
        try:
            if self.path.exists():
                pid = int(self.path.read_text().strip())
                if pid == os.getpid():
                    self.path.unlink(missing_ok=True)
        except (ValueError, OSError):
            self.path.unlink(missing_ok=True)

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(f"Another process holds the lock: {self.path}")
        return self

    def __exit__(self, *exc):
        self.release()
