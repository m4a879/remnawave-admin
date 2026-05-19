"""Cluster-wide online users snapshot recorder.

Periodically samples the sum of users_online across active (non-disabled,
connected) nodes and stores it in online_users_snapshots. Used by the
Trends tab to draw the avg/max online trend chart.
"""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 60        # 1 min — matches the 24h chart bucket
DEFAULT_WINDOW_MINUTES = 2           # online = unique users seen in last N minutes
DEFAULT_RETENTION_DAYS = 31
CLEANUP_EVERY_TICKS = 60 * 24        # once a day at 1-min ticks


class OnlineSnapshotRecorder:
    """Background loop that writes a single online-users sample on each tick."""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._tick_counter = 0

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Online snapshot recorder started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Online snapshot recorder stopped")

    def _interval_seconds(self) -> int:
        try:
            from shared.config_service import config_service
            return int(config_service.get(
                "online_snapshot_interval_seconds", DEFAULT_INTERVAL_SECONDS,
            ) or DEFAULT_INTERVAL_SECONDS)
        except Exception:
            return DEFAULT_INTERVAL_SECONDS

    def _retention_days(self) -> int:
        try:
            from shared.config_service import config_service
            return int(config_service.get(
                "online_snapshot_retention_days", DEFAULT_RETENTION_DAYS,
            ) or DEFAULT_RETENTION_DAYS)
        except Exception:
            return DEFAULT_RETENTION_DAYS

    def _window_minutes(self) -> int:
        try:
            from shared.config_service import config_service
            return int(config_service.get(
                "online_snapshot_window_minutes", DEFAULT_WINDOW_MINUTES,
            ) or DEFAULT_WINDOW_MINUTES)
        except Exception:
            return DEFAULT_WINDOW_MINUTES

    async def _capture(self) -> None:
        """Count unique users seen in the last window_minutes and append a snapshot row.

        Source: user_connections, which node-agent populates via /collector/batch every
        ~30 sec. SUM(nodes.users_online) was unreliable because that column only refreshes
        on Panel sync (rare and often zero).
        """
        from shared.database import db_service
        if not db_service.is_connected:
            return
        try:
            window = self._window_minutes()
            async with db_service.acquire() as conn:
                total = await conn.fetchval(
                    """
                    SELECT COUNT(DISTINCT user_uuid)
                    FROM user_connections
                    WHERE user_uuid IS NOT NULL
                      AND connected_at >= NOW() - make_interval(mins => $1)
                    """,
                    window,
                )
            await db_service.insert_online_users_snapshot(int(total or 0))
        except Exception as e:
            logger.warning("Online snapshot capture failed: %s", e)

    async def _maybe_cleanup(self) -> None:
        self._tick_counter += 1
        if self._tick_counter < CLEANUP_EVERY_TICKS:
            return
        self._tick_counter = 0
        from shared.database import db_service
        try:
            deleted = await db_service.cleanup_old_online_snapshots(self._retention_days())
            if deleted:
                logger.info("Online snapshots cleanup: removed %d old rows", deleted)
        except Exception as e:
            logger.warning("Online snapshots cleanup failed: %s", e)

    async def _run_loop(self) -> None:
        # Small initial delay so DB / Panel sync warms up first
        await asyncio.sleep(30)
        while self._running:
            try:
                await self._capture()
                await self._maybe_cleanup()
            except Exception as e:
                logger.warning("Online snapshot loop error: %s", e)
            try:
                await asyncio.sleep(self._interval_seconds())
            except asyncio.CancelledError:
                break


online_snapshot_recorder = OnlineSnapshotRecorder()
