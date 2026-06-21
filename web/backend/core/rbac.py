"""RBAC — Role-Based Access Control core module.

Provides:
- Database operations for roles and permissions
- Permission checking helpers (re-exported from shared/rbac.py)
- Caching layer for frequently-accessed permission data
- Access policy resolvers (scope, check, filter)

Admin account CRUD → core/admin_accounts.py
Audit log          → core/audit.py
"""
import logging
from typing import Optional, Dict, List, Set, Tuple

from shared.rbac import (
    _ensure_cache,
    _permissions_cache,
    invalidate_cache,
    has_permission,
    get_role_permissions,
    get_all_permissions_for_role_id,
    get_admin_account_by_telegram_id,
    get_admin_account_by_id as _get_admin_account_by_id_shared,
    get_scope as _get_scope_shared,
    filter_by_scope as _filter_by_scope_shared,
    get_visible_user_uuids as _get_visible_user_uuids_shared,
    invalidate_scope_cache,
    check_quota as _check_quota_shared,
)
from shared.db_schema import ADMIN_TABLE, ADMIN_ROLES_TABLE, ADMIN_PERMISSIONS_TABLE
from shared.db_query import select_sql, insert_sql, update_sql, delete_sql, left_join_sql, join_sql

# Re-export from shared/rbac.py so callers can import from here
from shared.rbac import (  # noqa: F401
    _ensure_cache,
    _permissions_cache,
    invalidate_cache,
    has_permission,
    get_role_permissions,
    get_all_permissions_for_role_id,
    get_admin_account_by_telegram_id,
    invalidate_scope_cache,
)

logger = logging.getLogger(__name__)


# ── Role database operations ────────────────────────────────────

async def list_roles() -> List[dict]:
    """List all roles with permission counts."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return []
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                select_sql(
                    ADMIN_ROLES_TABLE,
                    "r.*, COUNT(p.id) as permissions_count, COUNT(DISTINCT a.id) as admins_count",
                    (
                        f"r "
                        f"{left_join_sql(ADMIN_PERMISSIONS_TABLE, 'p', 'p.role_id = r.id')} "
                        f"{left_join_sql(ADMIN_TABLE, 'a', 'a.role_id = r.id')} "
                        f"GROUP BY r.id ORDER BY r.id ASC"
                    ),
                )
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("list_roles failed: %s", e)
        return []


async def get_role_by_id(role_id: int) -> Optional[dict]:
    """Fetch role with its permissions."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return None
        async with db_service.acquire() as conn:
            role = await conn.fetchrow(
                select_sql(
                    ADMIN_ROLES_TABLE,
                    "*",
                    "WHERE id = $1",
                ),
                role_id,
            )
            if not role:
                return None
            perms = await conn.fetch(
                select_sql(
                    ADMIN_PERMISSIONS_TABLE,
                    "resource, action",
                    "WHERE role_id = $1",
                ),
                role_id,
            )
            result = dict(role)
            result["permissions"] = [dict(p) for p in perms]
            return result
    except Exception as e:
        logger.error("get_role_by_id failed: %s", e)
        return None


async def get_role_by_name(name: str) -> Optional[dict]:
    """Fetch role by name."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return None
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(
                    ADMIN_ROLES_TABLE,
                    "*",
                    "WHERE name = $1",
                ),
                name,
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("get_role_by_name failed: %s", e)
        return None


async def create_role(
    name: str,
    display_name: str,
    description: Optional[str] = None,
    permissions: Optional[List[dict]] = None,
) -> Optional[dict]:
    """Create role with permissions. permissions = [{resource, action}, ...]"""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return None
        async with db_service.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    insert_sql(
                        ADMIN_ROLES_TABLE,
                        ["name", "display_name", "description", "is_system"],
                        values="$1, $2, $3, false",
                        returning="*",
                    ),
                    name, display_name, description,
                )
                role = dict(row)
                if permissions:
                    for p in permissions:
                        await conn.execute(
                            insert_sql(
                                ADMIN_PERMISSIONS_TABLE,
                                ["role_id", "resource", "action"],
                                suffix="ON CONFLICT DO NOTHING",
                            ),
                            role["id"], p["resource"], p["action"],
                        )
                invalidate_cache()
                role["permissions"] = permissions or []
                return role
    except Exception as e:
        logger.error("create_role failed: %s", e)
        return None


async def update_role(
    role_id: int,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    permissions: Optional[List[dict]] = None,
) -> Optional[dict]:
    """Update role and optionally replace all permissions."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return None
        async with db_service.acquire() as conn:
            async with conn.transaction():
                if display_name is not None or description is not None:
                    sets = []
                    vals = []
                    idx = 1
                    if display_name is not None:
                        sets.append(f"display_name = ${idx}")
                        vals.append(display_name)
                        idx += 1
                    if description is not None:
                        sets.append(f"description = ${idx}")
                        vals.append(description)
                        idx += 1
                    vals.append(role_id)
                    await conn.execute(
                        update_sql(
                            ADMIN_ROLES_TABLE,
                            ', '.join(sets),
                            f"id = ${idx}",
                        ),
                        *vals,
                    )

                if permissions is not None:
                    await conn.execute(
                        delete_sql(
                            ADMIN_PERMISSIONS_TABLE,
                            "role_id = $1",
                        ),
                        role_id,
                    )
                    for p in permissions:
                        await conn.execute(
                            insert_sql(
                                ADMIN_PERMISSIONS_TABLE,
                                ["role_id", "resource", "action"],
                            ),
                            role_id, p["resource"], p["action"],
                        )
                    invalidate_cache()

                return await get_role_by_id(role_id)
    except Exception as e:
        logger.error("update_role failed: %s", e)
        return None


async def delete_role(role_id: int) -> bool:
    """Delete a custom role (system roles cannot be deleted)."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return False
        async with db_service.acquire() as conn:
            result = await conn.execute(
                delete_sql(
                    ADMIN_ROLES_TABLE,
                    "id = $1 AND is_system = false",
                ),
                role_id,
            )
            if "DELETE 1" in result:
                invalidate_cache()
                return True
            return False
    except Exception as e:
        logger.error("delete_role failed: %s", e)
        return False


# ── Quota checking ──────────────────────────────────────────────

async def check_quota(admin_id: int, resource: str) -> Tuple[bool, str]:
    """Check if admin is within their resource quota. Delegates to shared."""
    return await _check_quota_shared(admin_id, resource)


# ── First-run RBAC setup ───────────────────────────────────────

async def ensure_rbac_tables() -> None:
    """Ensure RBAC tables exist (for use when Alembic hasn't run yet).

    This is a safety net — in production, use Alembic migrations.
    """
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'admin_accounts'"
            )
            if not row:
                logger.warning(
                    "RBAC tables not found. Run Alembic migrations: "
                    "alembic upgrade head"
                )
    except Exception as e:
        logger.warning("ensure_rbac_tables check failed: %s", e)


async def sync_superadmin_permissions() -> None:
    """Ensure the superadmin system role has ALL permissions, including plugin-contributed ones."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return

        from web.backend.api.v2.roles import get_resources_map
        resources_map = get_resources_map()

        async with db_service.acquire() as conn:
            role_row = await conn.fetchrow(
                select_sql(
                    ADMIN_ROLES_TABLE,
                    "id",
                    "WHERE name = 'superadmin'",
                ),
            )
            if not role_row:
                logger.debug("sync_superadmin_permissions: superadmin role not found, skipping")
                return

            role_id = role_row["id"]

            existing = await conn.fetch(
                select_sql(
                    ADMIN_PERMISSIONS_TABLE,
                    "resource, action",
                    "WHERE role_id = $1",
                ),
                role_id,
            )
            existing_set = {(row["resource"], row["action"]) for row in existing}

            full_set = set()
            for resource, actions in resources_map.items():
                for action in actions:
                    full_set.add((resource, action))

            missing = full_set - existing_set
            if not missing:
                return

            async with conn.transaction():
                for resource, action in sorted(missing):
                    await conn.execute(
                        insert_sql(
                            ADMIN_PERMISSIONS_TABLE,
                            ["role_id", "resource", "action"],
                            suffix="ON CONFLICT DO NOTHING",
                        ),
                        role_id, resource, action,
                    )

            invalidate_cache()
            logger.info(
                "sync_superadmin_permissions: added %d missing permissions: %s",
                len(missing),
                ", ".join(f"{r}:{a}" for r, a in sorted(missing)),
            )

    except Exception as e:
        logger.warning("sync_superadmin_permissions failed: %s", e)


# ── Access policies — scope resolver ─────────────────────────────

async def get_scope(
    admin, resource_type: str, action: str = "view",
) -> Optional[Set[str]]:
    """Resolve allowed resource UUIDs for an admin on (resource_type, action).

    AdminUser-aware wrapper around shared/rbac.py get_scope().

    Returns:
        None — full access (superadmin, legacy admin, or no policies attached)
        set[str] — whitelist of UUIDs (may be empty -> no access)
    """
    if admin is None:
        return None
    role = getattr(admin, "role", None)
    account_id = getattr(admin, "account_id", None)
    role_id = getattr(admin, "role_id", None)
    return await _get_scope_shared(account_id, role_id, role, resource_type, action)


async def check_access(
    admin, resource_type: str, resource_uuid: str, action: str = "view",
) -> bool:
    """Single-UUID access check. True = allowed."""
    scope = await get_scope(admin, resource_type, action)
    if scope is None:
        return True
    return resource_uuid.lower() in scope


def filter_by_scope(items: List[dict], scope: Optional[Set[str]], uuid_key: str = "uuid") -> List[dict]:
    """Filter a list of dicts by an allowed-UUID scope. Delegates to shared."""
    return _filter_by_scope_shared(items, scope, uuid_key)


async def get_visible_user_uuids(admin) -> Optional[Set[str]]:
    """Resolve which user UUIDs an admin can see.

    AdminUser-aware wrapper around shared/rbac.py get_visible_user_uuids().
    """
    if admin is None:
        return None
    role = getattr(admin, "role", None)
    account_id = getattr(admin, "account_id", None)
    return await _get_visible_user_uuids_shared(account_id, role)


async def resolve_allowed_actions_map(
    admin, resource_type: str, uuids: List[str],
) -> Dict[str, Optional[List[str]]]:
    """For a list of resource UUIDs, resolve which actions each one allows.

    Returns {uuid_lower: [actions] or None}.
    None = no restriction (superadmin or no policies). Empty list = hidden.
    Used to annotate list responses so the frontend can gate UI buttons.
    """
    view_scope = await get_scope(admin, resource_type, "view")
    if view_scope is None:
        return {u.lower(): None for u in uuids}
    edit_scope = await get_scope(admin, resource_type, "edit")
    delete_scope = await get_scope(admin, resource_type, "delete")
    result: Dict[str, Optional[List[str]]] = {}
    for u in uuids:
        key = u.lower()
        actions: List[str] = []
        if key in view_scope:
            actions.append("view")
        if edit_scope is not None and key in edit_scope:
            actions.append("edit")
        if delete_scope is not None and key in delete_scope:
            actions.append("delete")
        result[key] = actions
    return result


# ── Backward-compat re-exports ───────────────────────────────────
# These functions moved to core/admin_accounts.py and core/audit.py.
# Import from the new location for new code.

from web.backend.core.admin_accounts import (  # noqa: E402, F401
    invalidate_admin_cache,
    get_admin_account_by_username,
    get_admin_account_by_email,
    get_admin_account_by_id,
    list_admin_accounts,
    create_admin_account,
    update_admin_account,
    delete_admin_account,
    increment_usage_counter,
    admin_account_exists,
    get_admin_usernames,
)
from web.backend.core.audit import (  # noqa: E402, F401
    write_audit_log,
    get_audit_logs,
    get_audit_logs_for_resource,
    get_audit_distinct_actions,
)
