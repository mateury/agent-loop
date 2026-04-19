"""Built-in scheduler — runs heartbeat, digest, and maintain loops in-process."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from agent_loop.config import Config
from agent_loop.loops.heartbeat import run_heartbeat
from agent_loop.loops.digest import run_digest
from agent_loop.loops.maintain import run_maintain

log = logging.getLogger(__name__)


class LoopScheduler:
    """Manages autonomous loop scheduling.

    Runs loops as async tasks via APScheduler within the same event loop
    as the messenger bridge.
    """

    def __init__(self, config: Config, notify_fn=None):
        """
        Args:
            config: Agent configuration.
            notify_fn: Async function to send notifications (from bridge).
        """
        self.config = config
        self.notify_fn = notify_fn
        self._scheduler = AsyncIOScheduler()
        self._running = False

    def start(self):
        """Start the scheduler with configured loops."""
        hb = self.config.loops.heartbeat
        digest = self.config.loops.digest
        maintain = self.config.loops.maintain

        if hb.enabled:
            # Heartbeat: run every N minutes within active hours
            self._scheduler.add_job(
                self._run_heartbeat,
                "cron",
                minute=f"*/{hb.interval_minutes}",
                hour=f"{hb.active_hours_start}-{hb.active_hours_end}",
                id="heartbeat",
                max_instances=1,
                misfire_grace_time=60,
            )
            log.info(
                "Heartbeat scheduled: every %dm, %d:00-%d:00",
                hb.interval_minutes,
                hb.active_hours_start,
                hb.active_hours_end,
            )

        if digest.enabled:
            self._scheduler.add_job(
                self._run_digest,
                "cron",
                hour=digest.hour,
                minute=digest.minute,
                id="digest",
                max_instances=1,
                misfire_grace_time=300,
            )
            log.info("Digest scheduled: %02d:%02d", digest.hour, digest.minute)

        if maintain.enabled:
            self._scheduler.add_job(
                self._run_maintain,
                "cron",
                hour=f"*/{maintain.interval_hours}",
                minute=0,
                id="maintain",
                max_instances=1,
                misfire_grace_time=300,
            )
            log.info("Maintain scheduled: every %dh", maintain.interval_hours)

        self._scheduler.start()
        self._running = True
        log.info("Loop scheduler started")

    def stop(self):
        """Stop the scheduler."""
        if self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            log.info("Loop scheduler stopped")

    async def _run_heartbeat(self):
        """Execute heartbeat loop."""
        log.info("Running heartbeat...")
        try:
            output = await run_heartbeat(self.config)
            if output and self.notify_fn:
                await self.notify_fn(output)
        except Exception as e:
            log.error("Heartbeat failed: %s", e)
            if self.notify_fn:
                await self.notify_fn(f"Heartbeat failed: {e}")

    async def _run_digest(self):
        """Execute daily digest loop."""
        log.info("Running daily digest...")
        try:
            output = await run_digest(self.config)
            if output and self.notify_fn:
                await self.notify_fn(output)
        except Exception as e:
            log.error("Digest failed: %s", e)

    async def _run_maintain(self):
        """Execute memory maintenance loop."""
        log.info("Running memory maintenance...")
        try:
            output = await run_maintain(self.config)
            if output and self.notify_fn:
                await self.notify_fn(output)
        except Exception as e:
            log.error("Maintain failed: %s", e)

    @property
    def next_runs(self) -> dict[str, datetime | None]:
        """Get next scheduled run times for all jobs."""
        result = {}
        for job in self._scheduler.get_jobs():
            result[job.id] = job.next_run_time
        return result
