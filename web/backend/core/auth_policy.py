"""Политика метода входа на админа: какими способами он может логиниться.

Хранится в admin_accounts.allowed_auth_methods как JSON-массив. NULL/пусто =
все методы разрешены (дефолт, обратная совместимость). Проверяется на входе
для account-backed админов; легаси env-админы (без аккаунта) не ограничиваются.
"""
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Канонический порядок и полный набор способов входа.
AUTH_METHODS = ("password", "telegram", "passkey", "oauth")
_ALLOWED_SET = frozenset(AUTH_METHODS)


def parse_methods(raw: Any) -> Optional[List[str]]:
    """JSON-строку (или список) → список валидных методов; None если пусто/битое."""
    if raw is None:
        return None
    items = raw
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
        try:
            items = json.loads(raw)
        except (ValueError, TypeError):
            return None
    if not isinstance(items, (list, tuple)):
        return None
    valid = [m for m in AUTH_METHODS if m in set(items)]
    return valid or None


def serialize_methods(items: Optional[List[str]]) -> Optional[str]:
    """Список методов → JSON-строка для БД. Пусто/None/все → None (без ограничения)."""
    if not items:
        return None
    valid = [m for m in AUTH_METHODS if m in set(items)]
    # Разрешены все методы → политика не нужна, храним NULL.
    if not valid or len(valid) == len(AUTH_METHODS):
        return None
    return json.dumps(valid)


def method_allowed(account: Optional[Dict[str, Any]], method: str) -> bool:
    """Разрешён ли способ входа для аккаунта. Нет аккаунта/политики → да."""
    if not account:
        return True
    allowed = parse_methods(account.get("allowed_auth_methods"))
    if not allowed:
        return True
    return method in allowed
