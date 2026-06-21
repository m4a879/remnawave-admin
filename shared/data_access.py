"""
Data access helpers.
Provides unified access to data from database (primary) with API fallback.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Dict, List, Optional

from shared.database import db_service
from shared.api_client import api_client
from shared.logger import logger
from shared.db_schema import INTERNAL_SQUADS_TABLE, EXTERNAL_SQUADS_TABLE
from shared.db_query import select_sql


# ==================== Generic Helpers ====================

async def _fetch_single(
    id_value: str,
    db_method: Callable[[str], Awaitable[Optional[Dict[str, Any]]]],
    api_method: Callable[[str], Awaitable[Dict[str, Any]]],
    entity_name: str,
    id_field: str = "uuid",
) -> Optional[Dict[str, Any]]:
    if db_service.is_connected:
        result = await db_method(id_value)
        if result and result.get(id_field):
            logger.debug("%s %s fetched from DB", entity_name.title(), id_value)
            return result
    try:
        response = await api_method(id_value)
        data = response.get("response", {})
        if data:
            logger.debug("%s %s fetched from API (DB miss)", entity_name.title(), id_value)
            return data
    except Exception as e:
        logger.warning("Failed to fetch %s %s from API: %s", entity_name, id_value, e)
    return None


async def _fetch_single_wrapped(
    id_value: str,
    db_method: Callable[[str], Awaitable[Optional[Dict[str, Any]]]],
    api_method: Callable[[str], Awaitable[Dict[str, Any]]],
    entity_name: str,
    id_field: str = "uuid",
) -> Dict[str, Any]:
    if db_service.is_connected:
        result = await db_method(id_value)
        if result and result.get(id_field):
            logger.debug("%s %s fetched from DB (wrapped)", entity_name.title(), id_value)
            return {"response": result}
    return await api_method(id_value)


async def _fetch_list(
    db_method: Callable[[], Awaitable[List[Dict[str, Any]]]],
    api_method: Callable[[], Awaitable[Dict[str, Any]]],
    entity_name: str,
    response_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if db_service.is_connected:
        items = await db_method()
        if items:
            logger.debug("%s fetched from DB (%d)", entity_name.title(), len(items))
            return items
    try:
        response = await api_method()
        payload = response.get("response", {})
        if response_key is None:
            return payload if isinstance(payload, list) else []
        return payload.get(response_key, []) if isinstance(payload, dict) else []
    except Exception as e:
        logger.warning("Failed to fetch %s from API: %s", entity_name, e)
    return []


async def _fetch_list_wrapped(
    db_method: Callable[[], Awaitable[List[Dict[str, Any]]]],
    api_method: Callable[[], Awaitable[Dict[str, Any]]],
    entity_name: str,
) -> Dict[str, Any]:
    if db_service.is_connected:
        items = await db_method()
        if items:
            logger.debug("%s fetched from DB (wrapped, %d)", entity_name.title(), len(items))
            return {"response": items}
    return await api_method()


# ==================== User Access ====================

async def get_user_by_uuid(uuid: str) -> Optional[Dict[str, Any]]:
    return await _fetch_single(uuid, db_service.get_user_by_uuid, api_client.get_user_by_uuid, "user")


async def get_user_by_uuid_wrapped(uuid: str) -> Dict[str, Any]:
    return await _fetch_single_wrapped(uuid, db_service.get_user_by_uuid, api_client.get_user_by_uuid, "user")


async def get_user_by_short_uuid(short_uuid: str) -> Optional[Dict[str, Any]]:
    return await _fetch_single(short_uuid, db_service.get_user_by_short_uuid, api_client.get_user_by_short_uuid, "user")


# ==================== Token Access ====================

async def get_all_tokens() -> List[Dict[str, Any]]:
    """Get all API tokens. Tries DB first, falls back to API."""
    if db_service.is_connected:
        tokens = await db_service.get_all_tokens()
        if tokens:
            logger.debug("Tokens fetched from DB (%d)", len(tokens))
            return tokens
    
    try:
        response = await api_client.get_tokens()
        payload = response.get("response", {})
        
        # Handle different response formats
        if isinstance(payload, list):
            return payload
        elif isinstance(payload, dict):
            return payload.get("apiKeys") or payload.get("tokens") or []
    except Exception as e:
        logger.warning("Failed to fetch tokens from API: %s", e)
    
    return []


async def get_token_by_uuid(uuid: str) -> Optional[Dict[str, Any]]:
    """Get token by UUID. Tries DB first, falls back to API."""
    if db_service.is_connected:
        token = await db_service.get_token_by_uuid(uuid)
        if token and token.get("uuid"):
            return token
    
    # API doesn't have get_token_by_uuid, so search in list
    tokens = await get_all_tokens()
    return next((t for t in tokens if t.get("uuid") == uuid), None)


# ==================== Template Access ====================

async def get_all_templates() -> List[Dict[str, Any]]:
    return await _fetch_list(db_service.get_all_templates, api_client.get_templates, "templates", "subscriptionTemplates")


async def get_template_by_uuid(uuid: str) -> Optional[Dict[str, Any]]:
    return await _fetch_single(uuid, db_service.get_template_by_uuid, api_client.get_template, "template")


# ==================== Snippet Access ====================

async def get_all_snippets() -> List[Dict[str, Any]]:
    return await _fetch_list(db_service.get_all_snippets, api_client.get_snippets, "snippets", "snippets")


async def get_snippet_by_name(name: str) -> Optional[Dict[str, Any]]:
    return await _fetch_single(name, db_service.get_snippet_by_name, api_client.get_snippet, "snippet", id_field="name")


# ==================== Squad Access ====================

async def get_all_internal_squads() -> List[Dict[str, Any]]:
    return await _fetch_list(db_service.get_all_internal_squads, api_client.get_internal_squads, "internal squads", "internalSquads")


async def get_all_external_squads() -> List[Dict[str, Any]]:
    return await _fetch_list(db_service.get_all_external_squads, api_client.get_external_squads, "external squads", "externalSquads")


async def get_all_squads() -> tuple[List[Dict[str, Any]], str]:
    """
    Get all squads (internal first, then external if empty).
    Returns tuple of (squads_list, source) where source is "internal" or "external".
    """
    squads = await get_all_internal_squads()
    if squads:
        return squads, "internal"
    
    squads = await get_all_external_squads()
    return squads, "external"


async def get_squads_for_admin(
    account_id: Optional[int],
    role_id: Optional[int],
    role: Optional[str],
) -> tuple[List[Dict[str, Any]], str]:
    """
    Get squads filtered by admin's access scope.
    Returns tuple of (squads_list, source) where source is "internal" or "external".
    """
    from shared.rbac import get_scope
    
    squad_scope = await get_scope(account_id, role_id, role, "squad", "view")
    
    # If no scope restriction (superadmin, legacy, or no policies), return all squads
    if squad_scope is None:
        return await get_all_squads()
    
    # If scope is empty set, admin has no access to any squads
    if not squad_scope:
        return [], "internal"
    
    squad_list = list(squad_scope)
    
    # Fetch internal squads that match the scope
    if db_service.is_connected:
        try:
            rows = await db_service._pool.fetch(
                select_sql(
                    INTERNAL_SQUADS_TABLE,
                    "*",
                    "WHERE uuid = ANY($1::uuid[])",
                ),
                squad_list
            )
            internal_squads = [dict(row) for row in rows]
            if internal_squads:
                return internal_squads, "internal"
        except Exception as e:
            logger.warning("Failed to fetch internal squads for admin scope: %s", e)
    
    # Fallback to API for internal squads
    try:
        response = await api_client.get_internal_squads()
        payload = response.get("response", {})
        all_internal = payload.get("internalSquads", []) if isinstance(payload, dict) else []
        filtered = [s for s in all_internal if s.get("uuid", "").lower() in squad_scope]
        if filtered:
            return filtered, "internal"
    except Exception as e:
        logger.warning("Failed to fetch internal squads from API for admin scope: %s", e)
    
    # If no internal squads match, try external squads
    if db_service.is_connected:
        try:
            rows = await db_service._pool.fetch(
                select_sql(
                    EXTERNAL_SQUADS_TABLE,
                    "*",
                    "WHERE uuid = ANY($1::uuid[])",
                ),
                squad_list
            )
            external_squads = [dict(row) for row in rows]
            if external_squads:
                return external_squads, "external"
        except Exception as e:
            logger.warning("Failed to fetch external squads for admin scope: %s", e)
    
    # Fallback to API for external squads
    try:
        response = await api_client.get_external_squads()
        payload = response.get("response", {})
        all_external = payload.get("externalSquads", []) if isinstance(payload, dict) else []
        filtered = [s for s in all_external if s.get("uuid", "").lower() in squad_scope]
        return filtered, "external"
    except Exception as e:
        logger.warning("Failed to fetch external squads from API for admin scope: %s", e)
    
    return [], "internal"


# ==================== Host Access ====================

async def get_all_hosts() -> List[Dict[str, Any]]:
    return await _fetch_list(db_service.get_all_hosts, api_client.get_hosts, "hosts")


async def get_all_hosts_wrapped() -> Dict[str, Any]:
    return await _fetch_list_wrapped(db_service.get_all_hosts, api_client.get_hosts, "hosts")


# ==================== Node Access ====================

async def get_all_nodes() -> List[Dict[str, Any]]:
    return await _fetch_list(db_service.get_all_nodes, api_client.get_nodes, "nodes")


async def get_all_nodes_wrapped() -> Dict[str, Any]:
    return await _fetch_list_wrapped(db_service.get_all_nodes, api_client.get_nodes, "nodes")
