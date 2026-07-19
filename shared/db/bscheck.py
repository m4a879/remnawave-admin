"""БС-проверки нод (bschekbot) — история результатов probe по ноде."""
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
    async def save_bscheck(self, node_uuid: str, passed: int, total: int,
                           cost_credits: Optional[int], result: Dict[str, Any],
                           created_by: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        async with self.acquire() as conn:
            r = await conn.fetchrow(
                f"""INSERT INTO {NODE_BSCHECK_TABLE}
                    (node_uuid, passed, total, cost_credits, result, created_by)
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6) RETURNING *""",
                node_uuid, passed, total, cost_credits,
                json.dumps(result, ensure_ascii=False), created_by,
            )
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

    async def get_bscheck_summary_map(self) -> Dict[str, Dict[str, Any]]:
        """Последний результат по каждой ноде — для бейджей в списке нод."""
        if not self.is_connected:
            return {}
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT DISTINCT ON (node_uuid) node_uuid, passed, total, checked_at
                    FROM {NODE_BSCHECK_TABLE} ORDER BY node_uuid, checked_at DESC""")
        out: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            out[r["node_uuid"]] = {
                "passed": r["passed"], "total": r["total"],
                "checked_at": r["checked_at"].isoformat() if r["checked_at"] else None,
            }
        return out
