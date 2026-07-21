"""Buffered last_used_at updates for API keys.

Avoids UPDATE-per-request row lock under high RPS. Collects "key used" events
in memory and flushes to DB every N seconds.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_FLUSH_INTERVAL_SEC = float(os.getenv("API_KEY_LAST_USED_FLUSH_SEC", "30"))

_pending: dict[int, float] = {}
_lock = asyncio.Lock()
_flush_task: Optional[asyncio.Task] = None
_stop = asyncio.Event()


async def mark_used(key_id: int) -> None:
    """Record that a key was used. Flushed asynchronously."""
    async with _lock:
        import time
        _pending[key_id] = time.time()


async def _flush() -> None:
    async with _lock:
        if not _pending:
            return
        snapshot = dict(_pending)
        _pending.clear()
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return
        async with db_service.acquire() as conn:
            for key_id, ts in snapshot.items():
                from datetime import datetime, timezone
                await conn.execute(
                    "UPDATE api_keys SET last_used_at = $2 WHERE id = $1",
                    key_id, datetime.fromtimestamp(ts, tz=timezone.utc),
                )
    except Exception as e:
        logger.warning("Failed to flush API key last_used_at: %s", e)


async def _loop() -> None:
    logger.debug("API key usage buffer started (interval=%ss)", _FLUSH_INTERVAL_SEC)
    while not _stop.is_set():
        try:
            await asyncio.wait_for(_stop.wait(), timeout=_FLUSH_INTERVAL_SEC)
        except asyncio.TimeoutError:
            pass
        await _flush()
    await _flush()
    logger.info("API key usage buffer stopped")


def start() -> None:
    global _flush_task
    if _flush_task and not _flush_task.done():
        return
    _stop.clear()
    _flush_task = asyncio.create_task(_loop(), name="api-key-usage-flush")


async def stop() -> None:
    _stop.set()
    if _flush_task:
        try:
            await asyncio.wait_for(_flush_task, timeout=5)
        except asyncio.TimeoutError:
            _flush_task.cancel()
