"""История версий конфигов (профили xray / шаблоны / сниппеты).

Снапшот при каждом сохранении через наш API: дедуп по content_hash
(одинаковые подряд не пишем), ретенция — последние KEEP_VERSIONS
на сущность.
"""
import hashlib
from typing import Any, Dict, List, Optional

from shared.db_schema import CONFIG_VERSIONS_TABLE

KEEP_VERSIONS = 30


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class ConfigVersionsMixin:
    async def save_config_version(
        self, entity_type: str, entity_id: str, content: str,
        entity_name: Optional[str] = None, created_by: Optional[str] = None,
    ) -> Optional[int]:
        """Сохранить снапшот. Возвращает id версии или None (дубль/нет БД)."""
        if not self.is_connected or not content:
            return None
        content_hash = _hash(content)
        async with self.acquire() as conn:
            last = await conn.fetchval(
                f"""SELECT content_hash FROM {CONFIG_VERSIONS_TABLE}
                    WHERE entity_type = $1 AND entity_id = $2
                    ORDER BY created_at DESC, id DESC LIMIT 1""",
                entity_type, entity_id,
            )
            if last == content_hash:
                return None  # содержимое не менялось
            version_id = await conn.fetchval(
                f"""INSERT INTO {CONFIG_VERSIONS_TABLE}
                    (entity_type, entity_id, entity_name, content, content_hash, created_by)
                    VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
                entity_type, entity_id, entity_name, content, content_hash, created_by,
            )
            # ретенция: держим последние KEEP_VERSIONS
            await conn.execute(
                f"""DELETE FROM {CONFIG_VERSIONS_TABLE}
                    WHERE entity_type = $1 AND entity_id = $2 AND id NOT IN (
                        SELECT id FROM {CONFIG_VERSIONS_TABLE}
                        WHERE entity_type = $1 AND entity_id = $2
                        ORDER BY created_at DESC, id DESC LIMIT $3
                    )""",
                entity_type, entity_id, KEEP_VERSIONS,
            )
        return version_id

    async def list_config_versions(
        self, entity_type: str, entity_id: str, limit: int = KEEP_VERSIONS,
    ) -> List[Dict[str, Any]]:
        """Список версий без content (метаданные + размер)."""
        if not self.is_connected:
            return []
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT id, entity_name, created_by, created_at,
                           LENGTH(content) AS size_bytes
                    FROM {CONFIG_VERSIONS_TABLE}
                    WHERE entity_type = $1 AND entity_id = $2
                    ORDER BY created_at DESC, id DESC LIMIT $3""",
                entity_type, entity_id, limit,
            )
        return [
            dict(r) | {"created_at": r["created_at"].isoformat() if r["created_at"] else None}
            for r in rows
        ]

    async def get_config_version(self, version_id: int) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT * FROM {CONFIG_VERSIONS_TABLE} WHERE id = $1", version_id,
            )
        if not row:
            return None
        d = dict(row)
        d["created_at"] = d["created_at"].isoformat() if d.get("created_at") else None
        return d
