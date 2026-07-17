"""Снапшоты онлайна для таба «Тренды».

Тренд должен показывать ту же метрику, что карточка «Сейчас онлайн» на
дашборде — SUM(nodes.users_online), панельный онлайн. Раньше рекордер считал
уникальных юзеров по user_connections, и графики расходились с дашбордом.
Фолбэк на user_connections остаётся для случая нулевой/отставшей панельной
суммы (синк нод отстаёт) — иначе график пустеет.
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from web.backend.core.online_snapshot_recorder import OnlineSnapshotRecorder


class FakeConn:
    def __init__(self, nodes_sum, conn_count):
        self.nodes_sum = nodes_sum
        self.conn_count = conn_count
        self.queries = []

    async def fetchval(self, query, *args):
        self.queries.append(query)
        if "FROM nodes" in query:
            return self.nodes_sum
        return self.conn_count


def _db(conn):
    db = AsyncMock()
    db.is_connected = True

    @asynccontextmanager
    async def acquire():
        yield conn

    db.acquire = acquire
    db.insert_online_users_snapshot = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_snapshot_uses_dashboard_nodes_sum():
    """Панельная сумма > 0 -> она и пишется, фолбэк-запрос не выполняется."""
    conn = FakeConn(nodes_sum=42, conn_count=99)
    db = _db(conn)
    with patch("shared.database.db_service", db):
        await OnlineSnapshotRecorder()._capture()
    db.insert_online_users_snapshot.assert_awaited_once_with(42)
    assert len(conn.queries) == 1


@pytest.mark.asyncio
async def test_snapshot_falls_back_to_connections_when_panel_zero():
    """Панельная сумма 0 (синк нод отстал) -> счёт по user_connections."""
    conn = FakeConn(nodes_sum=0, conn_count=7)
    db = _db(conn)
    with patch("shared.database.db_service", db):
        await OnlineSnapshotRecorder()._capture()
    db.insert_online_users_snapshot.assert_awaited_once_with(7)
    assert len(conn.queries) == 2
