"""
Resources mixin — hosts, config profiles, sync metadata, API tokens, templates, snippets, squads.
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shared.logger import logger
from shared.db_schema import (
    HOSTS_TABLE, CONFIG_PROFILES_TABLE, SYNC_METADATA_TABLE,
    API_TOKENS_TABLE, TEMPLATES_TABLE, SNIPPETS_TABLE,
    INTERNAL_SQUADS_TABLE, EXTERNAL_SQUADS_TABLE, NODES_TABLE,
)
from shared.db_query import select_sql, insert_sql, update_sql, delete_sql
from shared.metrics import SYNC_RUNS
from shared.db._base import _db_row_to_api_format, _parse_timestamp


class ResourcesMixin:
    # ==================== Hosts ====================

    async def get_all_hosts(self) -> List[Dict[str, Any]]:
        """Get all hosts with raw_data in API format."""
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(HOSTS_TABLE, "*", "ORDER BY remark")
            )
            return [_db_row_to_api_format(row) for row in rows]
    
    async def get_host_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get host by UUID with raw_data in API format."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(HOSTS_TABLE, "*", "WHERE uuid = $1"),
                uuid
            )
            return _db_row_to_api_format(row) if row else None
    
    async def get_hosts_stats(self) -> Dict[str, int]:
        """
        Get hosts statistics.
        Returns dict: {total, enabled, disabled}
        """
        if not self.is_connected:
            return {"total": 0, "enabled": 0, "disabled": 0}
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(HOSTS_TABLE, """
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE NOT is_disabled) as enabled,
                    COUNT(*) FILTER (WHERE is_disabled) as disabled
                """)
            )
            return dict(row) if row else {"total": 0, "enabled": 0, "disabled": 0}
    
    async def upsert_host(self, host_data: Dict[str, Any]) -> None:
        """Insert or update a host."""
        if not self.is_connected:
            return
        
        response = host_data.get("response", host_data)
        
        uuid = response.get("uuid")
        if not uuid:
            logger.warning("Cannot upsert host without UUID")
            return
        
        async with self.acquire() as conn:
            await conn.execute(
                insert_sql(
                    HOSTS_TABLE,
                    ["uuid", "remark", "address", "port", "is_disabled", "updated_at", "raw_data"],
                    values="$1, $2, $3, $4, $5, NOW(), $6",
                    suffix="""ON CONFLICT (uuid) DO UPDATE SET
                    remark = EXCLUDED.remark,
                    address = EXCLUDED.address,
                    port = EXCLUDED.port,
                    is_disabled = EXCLUDED.is_disabled,
                    updated_at = NOW(),
                    raw_data = EXCLUDED.raw_data""",
                ),
                uuid,
                response.get("remark"),
                response.get("address"),
                response.get("port"),
                response.get("isDisabled", False),
                json.dumps(response),
            )
    
    async def bulk_upsert_hosts(self, hosts: List[Dict[str, Any]]) -> int:
        """Bulk insert or update hosts. Returns number of records processed."""
        if not self.is_connected or not hosts:
            return 0
        
        count = 0
        async with self.acquire() as conn:
            async with conn.transaction():
                for host_data in hosts:
                    try:
                        await self.upsert_host(host_data)
                        count += 1
                    except Exception as e:
                        logger.warning("Failed to upsert host: %s", e)
        
        return count
    
    async def delete_host(self, uuid: str) -> bool:
        """Delete host by UUID."""
        if not self.is_connected:
            return False
        
        async with self.acquire() as conn:
            result = await conn.execute(
                delete_sql(HOSTS_TABLE, "uuid = $1"),
                uuid
            )
            return result == "DELETE 1"
    
    # ==================== Config Profiles ====================
    
    async def get_all_config_profiles(self) -> List[Dict[str, Any]]:
        """Get all config profiles with raw_data in API format."""
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(CONFIG_PROFILES_TABLE, "*", "ORDER BY name")
            )
            return [_db_row_to_api_format(row) for row in rows]
    
    async def get_config_profile_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get config profile by UUID with raw_data in API format."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(CONFIG_PROFILES_TABLE, "*", "WHERE uuid = $1"),
                uuid
            )
            return _db_row_to_api_format(row) if row else None
    
    async def upsert_config_profile(self, profile_data: Dict[str, Any]) -> None:
        """Insert or update a config profile."""
        if not self.is_connected:
            return
        
        response = profile_data.get("response", profile_data)
        
        uuid = response.get("uuid")
        if not uuid:
            logger.warning("Cannot upsert config profile without UUID")
            return
        
        async with self.acquire() as conn:
            await conn.execute(
                insert_sql(
                    CONFIG_PROFILES_TABLE,
                    ["uuid", "name", "updated_at", "raw_data"],
                    values="$1, $2, NOW(), $3",
                    suffix="""ON CONFLICT (uuid) DO UPDATE SET
                    name = EXCLUDED.name,
                    updated_at = NOW(),
                    raw_data = EXCLUDED.raw_data""",
                ),
                uuid,
                response.get("name"),
                json.dumps(response),
            )
    
    async def bulk_upsert_config_profiles(self, profiles: List[Dict[str, Any]]) -> int:
        """Bulk insert or update config profiles. Returns number of records processed."""
        if not self.is_connected or not profiles:
            return 0
        
        count = 0
        async with self.acquire() as conn:
            async with conn.transaction():
                for profile_data in profiles:
                    try:
                        await self.upsert_config_profile(profile_data)
                        count += 1
                    except Exception as e:
                        logger.warning("Failed to upsert config profile: %s", e)
        
        return count
    
    # ==================== Sync Metadata ====================
    
    async def get_sync_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        """Get sync metadata by key."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(SYNC_METADATA_TABLE, "*", "WHERE key = $1"),
                key
            )
            return dict(row) if row else None
    
    async def update_sync_metadata(
        self,
        key: str,
        status: str,
        records_synced: int = 0,
        error_message: Optional[str] = None
    ) -> None:
        """Update sync metadata."""
        if not self.is_connected:
            return

        async with self.acquire() as conn:
            await conn.execute(
                insert_sql(
                    SYNC_METADATA_TABLE,
                    ["key", "last_sync_at", "sync_status", "records_synced", "error_message"],
                    values="$1, NOW(), $2, $3, $4",
                    suffix="""ON CONFLICT (key) DO UPDATE SET
                    last_sync_at = NOW(),
                    sync_status = EXCLUDED.sync_status,
                    records_synced = EXCLUDED.records_synced,
                    error_message = EXCLUDED.error_message""",
                ),
                key, status, records_synced, error_message
            )

        SYNC_RUNS.labels(
            kind=key,
            result="ok" if status == "success" else "error",
        ).inc()
    

    # ==================== API Tokens Methods ====================
    
    async def upsert_token(self, data: Dict[str, Any]) -> bool:
        """Upsert an API token."""
        if not self.is_connected:
            return False
        
        response = data.get("response", data)
        if isinstance(response, list):
            for token in response:
                await self._upsert_single_token(token)
            return True
        
        return await self._upsert_single_token(response)
    
    async def _upsert_single_token(self, token: Dict[str, Any]) -> bool:
        """Upsert a single token."""
        uuid = token.get("uuid")
        if not uuid:
            return False
        
        async with self.acquire() as conn:
            await conn.execute(
                insert_sql(
                    API_TOKENS_TABLE,
                    ["uuid", "name", "token_hash", "created_at", "updated_at", "raw_data"],
                    values="$1, $2, $3, $4, NOW(), $5",
                    suffix="""ON CONFLICT (uuid) DO UPDATE SET
                    name = EXCLUDED.name,
                    token_hash = EXCLUDED.token_hash,
                    updated_at = NOW(),
                    raw_data = EXCLUDED.raw_data""",
                ),
                uuid,
                token.get("name") or token.get("tokenName"),
                token.get("token") or token.get("tokenHash"),
                _parse_timestamp(token.get("createdAt")),
                json.dumps(token)
            )
        return True
    
    async def get_all_tokens(self) -> List[Dict[str, Any]]:
        """Get all API tokens."""
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(API_TOKENS_TABLE, "*", "ORDER BY name")
            )
            return [_db_row_to_api_format(row) for row in rows]
    
    async def get_token_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get token by UUID."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(API_TOKENS_TABLE, "*", "WHERE uuid = $1"),
                uuid
            )
            return _db_row_to_api_format(row) if row else None
    
    async def delete_token_from_db(self, uuid: str) -> bool:
        """Delete token from DB by UUID."""
        if not self.is_connected:
            return False
        
        async with self.acquire() as conn:
            result = await conn.execute(
                delete_sql(API_TOKENS_TABLE, "uuid = $1"),
                uuid
            )
            return result == "DELETE 1"
    
    async def delete_all_tokens(self) -> int:
        """Delete all tokens. Returns count of deleted records."""
        if not self.is_connected:
            return 0
        
        async with self.acquire() as conn:
            result = await conn.execute(delete_sql(API_TOKENS_TABLE, "TRUE"))
            try:
                return int(result.split()[-1])
            except (IndexError, ValueError):
                return 0

    # ==================== Templates Methods ====================
    
    async def upsert_template(self, data: Dict[str, Any]) -> bool:
        """Upsert a subscription template."""
        if not self.is_connected:
            return False
        
        response = data.get("response", data)
        if isinstance(response, list):
            for tpl in response:
                await self._upsert_single_template(tpl)
            return True
        
        return await self._upsert_single_template(response)
    
    async def _upsert_single_template(self, tpl: Dict[str, Any]) -> bool:
        """Upsert a single template."""
        uuid = tpl.get("uuid")
        if not uuid:
            return False
        
        async with self.acquire() as conn:
            await conn.execute(
                insert_sql(
                    TEMPLATES_TABLE,
                    ["uuid", "name", "template_type", "sort_order", "created_at", "updated_at", "raw_data"],
                    values="$1, $2, $3, $4, $5, NOW(), $6",
                    suffix="""ON CONFLICT (uuid) DO UPDATE SET
                    name = EXCLUDED.name,
                    template_type = EXCLUDED.template_type,
                    sort_order = EXCLUDED.sort_order,
                    updated_at = NOW(),
                    raw_data = EXCLUDED.raw_data""",
                ),
                uuid,
                tpl.get("name"),
                tpl.get("type") or tpl.get("templateType"),
                tpl.get("sortOrder") or tpl.get("sort_order"),
                _parse_timestamp(tpl.get("createdAt")),
                json.dumps(tpl)
            )
        return True
    
    async def get_all_templates(self) -> List[Dict[str, Any]]:
        """Get all subscription templates."""
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(TEMPLATES_TABLE, "*", "ORDER BY sort_order, name")
            )
            return [_db_row_to_api_format(row) for row in rows]
    
    async def get_template_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get template by UUID."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(TEMPLATES_TABLE, "*", "WHERE uuid = $1"),
                uuid
            )
            return _db_row_to_api_format(row) if row else None
    
    async def delete_template_from_db(self, uuid: str) -> bool:
        """Delete template from DB by UUID."""
        if not self.is_connected:
            return False
        
        async with self.acquire() as conn:
            result = await conn.execute(
                delete_sql(TEMPLATES_TABLE, "uuid = $1"),
                uuid
            )
            return result == "DELETE 1"
    
    async def delete_all_templates(self) -> int:
        """Delete all templates. Returns count of deleted records."""
        if not self.is_connected:
            return 0
        
        async with self.acquire() as conn:
            result = await conn.execute(delete_sql(TEMPLATES_TABLE, "TRUE"))
            try:
                return int(result.split()[-1])
            except (IndexError, ValueError):
                return 0

    # ==================== Snippets Methods ====================
    
    async def upsert_snippet(self, data: Dict[str, Any]) -> bool:
        """Upsert a snippet."""
        if not self.is_connected:
            return False
        
        response = data.get("response", data)
        snippets = response.get("snippets", []) if isinstance(response, dict) else response
        
        if isinstance(snippets, list):
            for snippet in snippets:
                await self._upsert_single_snippet(snippet)
            return True
        
        return await self._upsert_single_snippet(response)
    
    async def _upsert_single_snippet(self, snippet: Dict[str, Any]) -> bool:
        """Upsert a single snippet."""
        name = snippet.get("name")
        if not name:
            return False
        
        async with self.acquire() as conn:
            await conn.execute(
                insert_sql(
                    SNIPPETS_TABLE,
                    ["name", "snippet_data", "created_at", "updated_at", "raw_data"],
                    values="$1, $2, $3, NOW(), $4",
                    suffix="""ON CONFLICT (name) DO UPDATE SET
                    snippet_data = EXCLUDED.snippet_data,
                    updated_at = NOW(),
                    raw_data = EXCLUDED.raw_data""",
                ),
                name,
                json.dumps(snippet.get("snippet", [])),
                _parse_timestamp(snippet.get("createdAt")),
                json.dumps(snippet)
            )
        return True
    
    async def get_all_snippets(self) -> List[Dict[str, Any]]:
        """Get all snippets."""
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(SNIPPETS_TABLE, "*", "ORDER BY name")
            )
            return [_db_row_to_api_format(row) for row in rows]
    
    async def get_snippet_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get snippet by name."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(SNIPPETS_TABLE, "*", "WHERE name = $1"),
                name
            )
            return _db_row_to_api_format(row) if row else None
    
    async def delete_snippet_from_db(self, name: str) -> bool:
        """Delete snippet from DB by name."""
        if not self.is_connected:
            return False
        
        async with self.acquire() as conn:
            result = await conn.execute(
                delete_sql(SNIPPETS_TABLE, "name = $1"),
                name
            )
            return result == "DELETE 1"
    
    async def delete_all_snippets(self) -> int:
        """Delete all snippets. Returns count of deleted records."""
        if not self.is_connected:
            return 0
        
        async with self.acquire() as conn:
            result = await conn.execute(delete_sql(SNIPPETS_TABLE, "TRUE"))
            try:
                return int(result.split()[-1])
            except (IndexError, ValueError):
                return 0

    # ==================== Squads Methods ====================
    
    async def upsert_internal_squads(self, data: Dict[str, Any]) -> bool:
        """Upsert internal squads."""
        if not self.is_connected:
            return False
        
        response = data.get("response", data)
        squads = response.get("internalSquads", []) if isinstance(response, dict) else response
        
        if isinstance(squads, list):
            for squad in squads:
                await self._upsert_single_internal_squad(squad)
            return True
        
        return await self._upsert_single_internal_squad(response)
    
    async def _upsert_single_internal_squad(self, squad: Dict[str, Any]) -> bool:
        """Upsert a single internal squad."""
        uuid = squad.get("uuid")
        if not uuid:
            return False

        name = squad.get("name") or squad.get("squadName") or squad.get("tag") or squad.get("squadTag")

        async with self.acquire() as conn:
            await conn.execute(
                insert_sql(
                    INTERNAL_SQUADS_TABLE,
                    ["uuid", "name", "description", "updated_at", "raw_data"],
                    values="$1, $2, $3, NOW(), $4",
                    suffix="""ON CONFLICT (uuid) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    updated_at = NOW(),
                    raw_data = EXCLUDED.raw_data""",
                ),
                uuid,
                name,
                squad.get("description"),
                json.dumps(squad)
            )
        return True
    
    async def upsert_external_squads(self, data: Dict[str, Any]) -> bool:
        """Upsert external squads."""
        if not self.is_connected:
            return False
        
        response = data.get("response", data)
        squads = response.get("externalSquads", []) if isinstance(response, dict) else response
        
        if isinstance(squads, list):
            for squad in squads:
                await self._upsert_single_external_squad(squad)
            return True
        
        return await self._upsert_single_external_squad(response)
    
    async def _upsert_single_external_squad(self, squad: Dict[str, Any]) -> bool:
        """Upsert a single external squad."""
        uuid = squad.get("uuid")
        if not uuid:
            return False

        name = squad.get("name") or squad.get("squadName") or squad.get("tag") or squad.get("squadTag")

        async with self.acquire() as conn:
            await conn.execute(
                insert_sql(
                    EXTERNAL_SQUADS_TABLE,
                    ["uuid", "name", "description", "updated_at", "raw_data"],
                    values="$1, $2, $3, NOW(), $4",
                    suffix="""ON CONFLICT (uuid) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    updated_at = NOW(),
                    raw_data = EXCLUDED.raw_data""",
                ),
                uuid,
                name,
                squad.get("description"),
                json.dumps(squad)
            )
        return True
    
    async def get_all_internal_squads(self) -> List[Dict[str, Any]]:
        """Get all internal squads."""
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(INTERNAL_SQUADS_TABLE, "*", "ORDER BY name")
            )
            return [_db_row_to_api_format(row) for row in rows]
    
    async def get_all_external_squads(self) -> List[Dict[str, Any]]:
        """Get all external squads."""
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(EXTERNAL_SQUADS_TABLE, "*", "ORDER BY name")
            )
            return [_db_row_to_api_format(row) for row in rows]
    
    async def delete_all_internal_squads(self) -> int:
        """Delete all internal squads. Returns count of deleted records."""
        if not self.is_connected:
            return 0
        
        async with self.acquire() as conn:
            result = await conn.execute(
                delete_sql(INTERNAL_SQUADS_TABLE, "TRUE")
            )
            try:
                return int(result.split()[-1])
            except (IndexError, ValueError):
                return 0
    
    async def delete_all_external_squads(self) -> int:
        """Delete all external squads. Returns count of deleted records."""
        if not self.is_connected:
            return 0
        
        async with self.acquire() as conn:
            result = await conn.execute(
                delete_sql(EXTERNAL_SQUADS_TABLE, "TRUE")
            )
            try:
                return int(result.split()[-1])
            except (IndexError, ValueError):
                return 0
