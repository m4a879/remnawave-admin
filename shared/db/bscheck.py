"""БС-проверки (bschekbot) — журнал результатов + сохранённые авто-тесты (jobs).

node_bscheck: и проверки нод (kind='node', node_uuid задан), и ad-hoc/авто
(kind='probe'|'scan'|'vless'). job_id связывает результат с авто-тестом.
bscheck_jobs: именованные тесты с индивидуальным интервалом/бюджетом/целями.
"""
import json
from typing import Any, Dict, List, Optional

from shared.db_schema import NODE_BSCHECK_TABLE, BSCHECK_JOBS_TABLE


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


def _job_row(r) -> Dict[str, Any]:
    d = dict(r)
    if isinstance(d.get("config"), str):
        try:
            d["config"] = json.loads(d["config"])
        except (ValueError, TypeError):
            d["config"] = {}
    for k in ("last_run_at", "created_at", "updated_at"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    return d


class BscheckMixin:
    async def _insert_bscheck(self, node_uuid: Optional[str], kind: str, target: Optional[str],
                              passed: int, total: int, cost_credits: Optional[int],
                              result: Dict[str, Any], created_by: Optional[str],
                              job_id: Optional[int] = None):
        async with self.acquire() as conn:
            return await conn.fetchrow(
                f"""INSERT INTO {NODE_BSCHECK_TABLE}
                    (node_uuid, kind, target, passed, total, cost_credits, result, created_by, job_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9) RETURNING *""",
                node_uuid, kind, target, passed, total, cost_credits,
                json.dumps(result, ensure_ascii=False), created_by, job_id,
            )

    async def save_bscheck(self, node_uuid: str, passed: int, total: int,
                           cost_credits: Optional[int], result: Dict[str, Any],
                           created_by: Optional[str] = None, target: Optional[str] = None,
                           job_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        r = await self._insert_bscheck(node_uuid, "node", target, passed, total,
                                       cost_credits, result, created_by, job_id)
        return _row(r) if r else None

    async def save_bscheck_run(self, kind: str, target: Optional[str], passed: int, total: int,
                               cost_credits: Optional[int], result: Dict[str, Any],
                               created_by: Optional[str] = None,
                               job_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Ad-hoc/авто проверка (probe/scan/vless) без ноды — в общий журнал."""
        if not self.is_connected:
            return None
        r = await self._insert_bscheck(None, kind, target, passed, total,
                                       cost_credits, result, created_by, job_id)
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

    async def list_bscheck_runs(self, limit: int = 50, kind: Optional[str] = None,
                                job_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Журнал проверок (новые сверху); опц. фильтр по kind / job_id."""
        if not self.is_connected:
            return []
        conds, vals = [], []
        if kind:
            vals.append(kind); conds.append(f"kind = ${len(vals)}")
        if job_id is not None:
            vals.append(job_id); conds.append(f"job_id = ${len(vals)}")
        where = f"WHERE {' AND '.join(conds)}" if conds else ""
        vals.append(limit)
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM {NODE_BSCHECK_TABLE} {where} ORDER BY checked_at DESC LIMIT ${len(vals)}",
                *vals)
        return [_row(r) for r in rows]

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

    # ── Авто-тесты (jobs) ────────────────────────────────────────

    async def list_bscheck_jobs(self) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        async with self.acquire() as conn:
            rows = await conn.fetch(f"SELECT * FROM {BSCHECK_JOBS_TABLE} ORDER BY id")
        return [_job_row(r) for r in rows]

    async def get_bscheck_job(self, job_id: int) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        async with self.acquire() as conn:
            r = await conn.fetchrow(f"SELECT * FROM {BSCHECK_JOBS_TABLE} WHERE id = $1", job_id)
        return _job_row(r) if r else None

    async def create_bscheck_job(self, name: str, kind: str, interval_minutes: int,
                                 config: Dict[str, Any], budget_daily: int, alert: bool,
                                 enabled: bool = True, created_by: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        async with self.acquire() as conn:
            r = await conn.fetchrow(
                f"""INSERT INTO {BSCHECK_JOBS_TABLE}
                    (name, kind, enabled, interval_minutes, config, budget_daily, alert, created_by)
                    VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8) RETURNING *""",
                name, kind, enabled, interval_minutes,
                json.dumps(config, ensure_ascii=False), budget_daily, alert, created_by)
        return _job_row(r) if r else None

    async def update_bscheck_job(self, job_id: int, **fields) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        allowed = {"name", "kind", "enabled", "interval_minutes", "config", "budget_daily", "alert"}
        sets, vals = [], []
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k == "config":
                vals.append(json.dumps(v, ensure_ascii=False)); sets.append(f"config = ${len(vals)}::jsonb")
            else:
                vals.append(v); sets.append(f"{k} = ${len(vals)}")
        if not sets:
            return await self.get_bscheck_job(job_id)
        sets.append("updated_at = NOW()")
        vals.append(job_id)
        async with self.acquire() as conn:
            r = await conn.fetchrow(
                f"UPDATE {BSCHECK_JOBS_TABLE} SET {', '.join(sets)} WHERE id = ${len(vals)} RETURNING *", *vals)
        return _job_row(r) if r else None

    async def delete_bscheck_job(self, job_id: int) -> bool:
        if not self.is_connected:
            return False
        async with self.acquire() as conn:
            res = await conn.execute(f"DELETE FROM {BSCHECK_JOBS_TABLE} WHERE id = $1", job_id)
        return isinstance(res, str) and res.endswith("1")

    async def touch_bscheck_job_run(self, job_id: int) -> None:
        if not self.is_connected:
            return
        async with self.acquire() as conn:
            await conn.execute(
                f"UPDATE {BSCHECK_JOBS_TABLE} SET last_run_at = NOW() WHERE id = $1", job_id)

    async def get_bscheck_spent_today_job(self, job_id: int) -> int:
        if not self.is_connected:
            return 0
        async with self.acquire() as conn:
            val = await conn.fetchval(
                f"""SELECT COALESCE(SUM(cost_credits), 0) FROM {NODE_BSCHECK_TABLE}
                    WHERE job_id = $1 AND checked_at >= date_trunc('day', NOW())""", job_id)
        return int(val or 0)

    async def get_bscheck_last_by_target(self, job_id: int, kind: str) -> Dict[str, str]:
        """Время последней проверки по каждой цели данного job/kind — для ротации батчей."""
        if not self.is_connected:
            return {}
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT target, MAX(checked_at) AS last FROM {NODE_BSCHECK_TABLE}
                    WHERE job_id = $1 AND kind = $2 AND target IS NOT NULL
                    GROUP BY target""", job_id, kind)
        return {r["target"]: r["last"].isoformat() for r in rows if r["last"]}
