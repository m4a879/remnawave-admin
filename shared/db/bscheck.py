"""БС-проверки (bschekbot) — единый журнал результатов probe/scan/vless.

node_bscheck хранит и проверки нод (kind='node', node_uuid задан — для бейджа и
истории по ноде), и ad-hoc проверки (kind='probe'|'scan'|'vless', node_uuid NULL).
"""
import json
from typing import Any, Dict, List, Optional

from shared.db_schema import NODE_BSCHECK_TABLE


def _row(r) -> Dict[str, Any]:
    d = dict(r)
    if isinstance(d.get("result"), str):
        try:
            d["result"] = json.loads(d["result"])
        except (ValueError, TypeError):
            d["result"] = {}
    if d.get("checked_at") is not None:
        d["checked_at"] = d["checked_at"].isoformat()
    return d


class BscheckMixin:
    async def _insert_bscheck(self, node_uuid: Optional[str], kind: str, target: Optional[str],
                              passed: int, total: int, cost_credits: Optional[int],
                              result: Dict[str, Any], created_by: Optional[str]):
        async with self.acquire() as conn:
            return await conn.fetchrow(
                f"""INSERT INTO {NODE_BSCHECK_TABLE}
                    (node_uuid, kind, target, passed, total, cost_credits, result, created_by)
                    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8) RETURNING *""",
                node_uuid, kind, target, passed, total, cost_credits,
                json.dumps(result, ensure_ascii=False), created_by,
            )

    async def save_bscheck(self, node_uuid: str, passed: int, total: int,
                           cost_credits: Optional[int], result: Dict[str, Any],
                           created_by: Optional[str] = None,
                           target: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        r = await self._insert_bscheck(node_uuid, "node", target, passed, total,
                                       cost_credits, result, created_by)
        return _row(r) if r else None

    async def save_bscheck_run(self, kind: str, target: Optional[str], passed: int, total: int,
                               cost_credits: Optional[int], result: Dict[str, Any],
                               created_by: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Ad-hoc проверка (probe/scan/vless) без ноды — в общий журнал."""
        if not self.is_connected:
            return None
        r = await self._insert_bscheck(None, kind, target, passed, total,
                                       cost_credits, result, created_by)
        return _row(r) if r else None

    async def get_last_bscheck(self, node_uuid: str) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        async with self.acquire() as conn:
            r = await conn.fetchrow(
                f"""SELECT * FROM {NODE_BSCHECK_TABLE} WHERE node_uuid = $1
                    ORDER BY checked_at DESC LIMIT 1""", node_uuid)
        return _row(r) if r else None

    async def list_bscheck(self, node_uuid: str, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT * FROM {NODE_BSCHECK_TABLE} WHERE node_uuid = $1
                    ORDER BY checked_at DESC LIMIT $2""", node_uuid, limit)
        return [_row(r) for r in rows]

    async def list_bscheck_runs(self, limit: int = 50, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        """Весь журнал проверок (ноды + ad-hoc), новые сверху; фильтр по kind опционален."""
        if not self.is_connected:
            return []
        async with self.acquire() as conn:
            if kind:
                rows = await conn.fetch(
                    f"""SELECT * FROM {NODE_BSCHECK_TABLE} WHERE kind = $1
                        ORDER BY checked_at DESC LIMIT $2""", kind, limit)
            else:
                rows = await conn.fetch(
                    f"""SELECT * FROM {NODE_BSCHECK_TABLE}
                        ORDER BY checked_at DESC LIMIT $1""", limit)
        return [_row(r) for r in rows]

    async def get_bscheck_last_run(self, created_by: str = "scheduler") -> Optional[str]:
        """Время последней авто-проверки (для интервала шедулера)."""
        if not self.is_connected:
            return None
        async with self.acquire() as conn:
            ts = await conn.fetchval(
                f"SELECT MAX(checked_at) FROM {NODE_BSCHECK_TABLE} WHERE created_by = $1", created_by)
        return ts.isoformat() if ts else None

    async def get_bscheck_spent_today(self, created_by: str = "scheduler") -> int:
        """Сумма кредитов, потраченных авто-проверкой сегодня (бюджет-гард)."""
        if not self.is_connected:
            return 0
        async with self.acquire() as conn:
            val = await conn.fetchval(
                f"""SELECT COALESCE(SUM(cost_credits), 0) FROM {NODE_BSCHECK_TABLE}
                    WHERE created_by = $1 AND checked_at >= date_trunc('day', NOW())""", created_by)
        return int(val or 0)

    async def get_bscheck_summary_map(self) -> Dict[str, Dict[str, Any]]:
        """Последний результат по каждой ноде — для бейджей в списке нод."""
        if not self.is_connected:
            return {}
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT DISTINCT ON (node_uuid) node_uuid, passed, total, checked_at
                    FROM {NODE_BSCHECK_TABLE} WHERE node_uuid IS NOT NULL
                    ORDER BY node_uuid, checked_at DESC""")
        out: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            out[r["node_uuid"]] = {
                "passed": r["passed"], "total": r["total"],
                "checked_at": r["checked_at"].isoformat() if r["checked_at"] else None,
            }
        return out
