"""Пресеты создания юзера — CRUD над user_presets.

Поля пресета — гибкий JSONB `data`; валидацию ключей делает API-слой.
"""
import json
from typing import Any, Dict, List, Optional

from shared.db_schema import USER_PRESETS_TABLE


def _row(r) -> Dict[str, Any]:
    d = dict(r)
    if isinstance(d.get("data"), str):
        try:
            d["data"] = json.loads(d["data"])
        except (ValueError, TypeError):
            d["data"] = {}
    for k in ("created_at", "updated_at"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    return d


class UserPresetsMixin:
    async def list_user_presets(self) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM {USER_PRESETS_TABLE} ORDER BY name"
            )
        return [_row(r) for r in rows]

    async def get_user_preset(self, preset_id: int) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        async with self.acquire() as conn:
            r = await conn.fetchrow(
                f"SELECT * FROM {USER_PRESETS_TABLE} WHERE id = $1", preset_id
            )
        return _row(r) if r else None

    async def create_user_preset(
        self, name: str, data: Dict[str, Any], created_by: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        async with self.acquire() as conn:
            r = await conn.fetchrow(
                f"""INSERT INTO {USER_PRESETS_TABLE} (name, data, created_by)
                    VALUES ($1, $2::jsonb, $3) RETURNING *""",
                name, json.dumps(data, ensure_ascii=False), created_by,
            )
        return _row(r) if r else None

    async def update_user_preset(
        self, preset_id: int, name: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        async with self.acquire() as conn:
            r = await conn.fetchrow(
                f"""UPDATE {USER_PRESETS_TABLE}
                    SET name = COALESCE($2, name),
                        data = COALESCE($3::jsonb, data),
                        updated_at = NOW()
                    WHERE id = $1 RETURNING *""",
                preset_id, name,
                json.dumps(data, ensure_ascii=False) if data is not None else None,
            )
        return _row(r) if r else None

    async def delete_user_preset(self, preset_id: int) -> bool:
        if not self.is_connected:
            return False
        async with self.acquire() as conn:
            result = await conn.execute(
                f"DELETE FROM {USER_PRESETS_TABLE} WHERE id = $1", preset_id
            )
        return "DELETE 1" in result
