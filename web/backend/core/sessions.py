"""Активные сессии админов — трек входов, список и отзыв.

Модель: каждый успешный вход account-backed админа создаёт строку в
``admin_sessions`` с идентификатором ``sid``. Тот же ``sid`` зашивается в
access/refresh JWT. Отзыв:
- строка (``revoked_at``) — источник истины, проверяется на refresh;
- in-memory-множество отозванных ``sid`` — быстрый гейт в ``get_current_admin``
  (немедленный эффект на том же воркере; на остальных access-токен доживает до
  истечения, затем refresh его добьёт — та же семантика, что у token_blacklist).

Легаси env-админы (без ``account_id``) не трекаются: ``create_session`` вернёт
None, и ``sid`` в токен не попадёт — их refresh работает как раньше.
"""
import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from shared.db_schema import ADMIN_SESSIONS_TABLE as TBL

logger = logging.getLogger(__name__)

_UA_MAX = 512

# ── In-memory кэш отзыва (sid -> ts истечения) ───────────────────────
_revoked: Dict[str, float] = {}
_lock = threading.Lock()
_last_cleanup = 0.0
_CLEANUP_INTERVAL = 300


def _mark_revoked_mem(sid: str, expires_at: float) -> None:
    global _last_cleanup
    with _lock:
        _revoked[sid] = expires_at
        now = time.time()
        if now - _last_cleanup >= _CLEANUP_INTERVAL:
            _last_cleanup = now
            for k in [k for k, v in _revoked.items() if v < now]:
                del _revoked[k]


def is_session_revoked(sid: str) -> bool:
    """Быстрая in-memory проверка (для hot-path get_current_admin)."""
    if not sid:
        return False
    with _lock:
        exp = _revoked.get(sid)
        if exp is None:
            return False
        if exp < time.time():
            del _revoked[sid]
            return False
        return True


def new_sid() -> str:
    return uuid.uuid4().hex


def _refresh_ttl_hours() -> int:
    from web.backend.core.security import get_refresh_ttl_hours
    return get_refresh_ttl_hours()


def _client_meta(request) -> tuple:
    """(ip, user_agent) из запроса; user_agent обрезается."""
    ip = None
    try:
        from web.backend.api.deps import get_client_ip
        ip = get_client_ip(request)
    except Exception:  # noqa: BLE001
        ip = None
    ua = (request.headers.get("user-agent") or "")[:_UA_MAX] if request is not None else ""
    return ip, (ua or None)


def _row(r) -> Dict[str, Any]:
    d = dict(r)
    for k in ("created_at", "last_seen_at", "expires_at", "revoked_at"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    return d


# ── Жизненный цикл ───────────────────────────────────────────────────

async def create_session(request, subject: str, account_id: Optional[int],
                         auth_method: str, username: str) -> Optional[str]:
    """Создать сессию для входа. Возвращает sid или None (легаси/БД недоступна)."""
    if account_id is None:
        return None
    from shared.database import db_service
    if not db_service.is_connected:
        return None
    sid = new_sid()
    ip, ua = _client_meta(request)
    try:
        async with db_service.acquire() as conn:
            await conn.execute(
                f"""INSERT INTO {TBL}
                    (id, account_id, auth_method, ip, user_agent, expires_at)
                    VALUES ($1, $2, $3, $4, $5, NOW() + ($6 || ' hours')::interval)""",
                sid, int(account_id), auth_method or "password", ip, ua, str(_refresh_ttl_hours()),
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("create_session failed: %s", e)
        return None
    return sid


async def validate_for_refresh(sid: str) -> bool:
    """True, если сессия существует, не отозвана и не истекла."""
    if not sid:
        return True  # токен без sid — трекинга нет, refresh как раньше
    from shared.database import db_service
    if not db_service.is_connected:
        return True  # не блокируем вход при недоступной БД
    async with db_service.acquire() as conn:
        r = await conn.fetchrow(
            f"SELECT revoked_at, expires_at FROM {TBL} WHERE id = $1", sid)
    if not r:
        return False  # строка была, теперь нет → отозвана/подчищена
    if r["revoked_at"] is not None:
        return False
    return True


async def touch_session(sid: str, request=None) -> None:
    """Обновить last_seen_at (+ ip/user_agent) на refresh."""
    if not sid:
        return
    from shared.database import db_service
    if not db_service.is_connected:
        return
    ip, ua = _client_meta(request) if request is not None else (None, None)
    try:
        async with db_service.acquire() as conn:
            if ip or ua:
                await conn.execute(
                    f"UPDATE {TBL} SET last_seen_at = NOW(), ip = COALESCE($2, ip), "
                    f"user_agent = COALESCE($3, user_agent) WHERE id = $1",
                    sid, ip, ua)
            else:
                await conn.execute(
                    f"UPDATE {TBL} SET last_seen_at = NOW() WHERE id = $1", sid)
    except Exception as e:  # noqa: BLE001
        logger.debug("touch_session: %s", e)


# ── Список / отзыв (self-service, scope по account_id) ───────────────

async def list_sessions(account_id: int) -> List[Dict[str, Any]]:
    from shared.database import db_service
    if not db_service.is_connected or account_id is None:
        return []
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT * FROM {TBL}
                WHERE account_id = $1 AND revoked_at IS NULL AND expires_at > NOW()
                ORDER BY last_seen_at DESC""",
            int(account_id))
    return [_row(r) for r in rows]


async def revoke_session(account_id: int, sid: str) -> bool:
    """Отозвать одну свою сессию (scoped). True — если строка обновлена."""
    if not sid or account_id is None:
        return False
    from shared.database import db_service
    if not db_service.is_connected:
        return False
    async with db_service.acquire() as conn:
        r = await conn.fetchrow(
            f"""UPDATE {TBL} SET revoked_at = NOW()
                WHERE id = $1 AND account_id = $2 AND revoked_at IS NULL
                RETURNING expires_at""",
            sid, int(account_id))
    if r:
        _mark_revoked_mem(sid, r["expires_at"].timestamp())
        return True
    return False


async def revoke_others(account_id: int, keep_sid: Optional[str]) -> int:
    """Отозвать все свои сессии, кроме keep_sid. Возвращает число отозванных."""
    if account_id is None:
        return 0
    from shared.database import db_service
    if not db_service.is_connected:
        return 0
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            f"""UPDATE {TBL} SET revoked_at = NOW()
                WHERE account_id = $1 AND revoked_at IS NULL
                  AND ($2::text IS NULL OR id <> $2)
                RETURNING id, expires_at""",
            int(account_id), keep_sid)
    for r in rows:
        _mark_revoked_mem(r["id"], r["expires_at"].timestamp())
    return len(rows)
