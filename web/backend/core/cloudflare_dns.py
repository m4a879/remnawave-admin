"""Cloudflare DNS — управление записями зон из админки.

Отдельно от финмодуль-адаптера Cloudflare (тот только читает домены с правами
Registrar:Read). Здесь нужен токен с правами Zone:Read + DNS:Edit.

Токен хранится зашифрованным (Fernet) в bot_config под ключом
`cloudflare_dns_token` — сам ключ регистрируется в config_service как секретный
и readonly (правится только через этот модуль, не через общий /settings).
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.crypto import encrypt_field, decrypt_field

logger = logging.getLogger(__name__)

CF_BASE = "https://api.cloudflare.com/client/v4"
_TOKEN_KEY = "cloudflare_dns_token"
_TIMEOUT = 20.0

#: типы записей, которыми управляем из UI
RECORD_TYPES = ["A", "AAAA", "CNAME", "TXT", "MX", "NS", "SRV", "CAA"]
#: типы, поддерживающие проксирование Cloudflare (оранжевое облако)
PROXYABLE = {"A", "AAAA", "CNAME"}


class CloudflareDnsError(Exception):
    """Ошибка Cloudflare DNS с человекочитаемым сообщением (уходит в API/UI)."""


# ── Хранение токена ──────────────────────────────────────────────

def _stored_token() -> Optional[str]:
    """Расшифрованный токен из конфига (None, если не настроен/битый)."""
    from shared.config_service import config_service
    enc = config_service.get(_TOKEN_KEY, None)
    if not enc:
        return None
    try:
        return decrypt_field(str(enc))
    except ValueError:
        logger.warning("Cloudflare DNS: токен не расшифровался (смена WEB_SECRET_KEY?)")
        return None


def is_configured() -> bool:
    return _stored_token() is not None


async def save_token(token: str) -> None:
    """Зашифровать и сохранить токен в bot_config + обновить кэш."""
    enc = encrypt_field(token.strip())
    await _write_config_value(enc)


async def clear_token() -> None:
    await _write_config_value("")


async def _write_config_value(value: str) -> None:
    from shared.database import db_service
    from shared.db_query import update_sql
    from shared.db_schema import BOT_CONFIG_TABLE
    from shared.config_service import config_service

    if not db_service.is_connected:
        raise CloudflareDnsError("База данных недоступна")
    async with db_service.acquire() as conn:
        await conn.execute(
            update_sql(BOT_CONFIG_TABLE, "value = $2, updated_at = NOW()", "key = $1"),
            _TOKEN_KEY, value,
        )
    # немедленный эффект без перезапуска
    try:
        if _TOKEN_KEY in config_service._cache:
            config_service._cache[_TOKEN_KEY].value = value
    except Exception as e:  # noqa: BLE001
        logger.debug("Cloudflare DNS: cache update skipped: %s", e)


# ── HTTP ─────────────────────────────────────────────────────────

async def _request(method: str, path: str, *, token: Optional[str] = None,
                   json_body: Optional[Dict[str, Any]] = None) -> Any:
    tok = token or _stored_token()
    if not tok:
        raise CloudflareDnsError("Cloudflare DNS токен не настроен")
    headers = {"Authorization": f"Bearer {tok}"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=headers,
                                     follow_redirects=True) as client:
            resp = await client.request(method, f"{CF_BASE}{path}", json=json_body)
    except httpx.HTTPError as e:
        raise CloudflareDnsError(f"Сеть/HTTP: {e}")
    if resp.status_code in (401, 403):
        raise CloudflareDnsError("Токен отклонён или нет прав (нужно Zone:Read + DNS:Edit)")
    try:
        data = resp.json()
    except ValueError:
        raise CloudflareDnsError(f"Некорректный ответ Cloudflare (HTTP {resp.status_code})")
    if isinstance(data, dict) and data.get("success") is False:
        errs = data.get("errors") or []
        msg = errs[0].get("message") if errs and isinstance(errs[0], dict) else f"HTTP {resp.status_code}"
        raise CloudflareDnsError(str(msg))
    if resp.status_code >= 400:
        raise CloudflareDnsError(f"Cloudflare HTTP {resp.status_code}")
    return data


async def verify_token(token: str) -> bool:
    """Проверить токен эндпоинтом /user/tokens/verify (не бросает — bool)."""
    try:
        data = await _request("GET", "/user/tokens/verify", token=token)
    except CloudflareDnsError:
        return False
    result = data.get("result") if isinstance(data, dict) else None
    return bool(isinstance(result, dict) and result.get("status") == "active")


# ── Зоны и записи ────────────────────────────────────────────────

def _zone(z: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": z.get("id"),
        "name": z.get("name"),
        "status": z.get("status"),
        "paused": z.get("paused"),
    }


def _record(r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": r.get("id"),
        "type": r.get("type"),
        "name": r.get("name"),
        "content": r.get("content"),
        "ttl": r.get("ttl"),
        "proxied": r.get("proxied"),
        "priority": r.get("priority"),
        "comment": r.get("comment"),
    }


async def list_zones() -> List[Dict[str, Any]]:
    data = await _request("GET", "/zones?per_page=50&order=name")
    result = data.get("result") if isinstance(data, dict) else None
    return [_zone(z) for z in (result or []) if isinstance(z, dict)]


async def list_records(zone_id: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    page = 1
    while page and len(out) < 1000:
        data = await _request(
            "GET", f"/zones/{zone_id}/dns_records?per_page=100&page={page}&order=type")
        for r in (data.get("result") or []):
            if isinstance(r, dict):
                out.append(_record(r))
        info = data.get("result_info") or {}
        total = info.get("total_pages")
        page = (page + 1) if (isinstance(total, int) and page < total) else None
    return out


def _build_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Собрать тело запроса к Cloudflare из проверенных полей."""
    rtype = str(payload.get("type") or "").upper()
    body: Dict[str, Any] = {
        "type": rtype,
        "name": str(payload.get("name") or "").strip(),
        "content": str(payload.get("content") or "").strip(),
        "ttl": int(payload.get("ttl") or 1),  # 1 = automatic
    }
    if rtype in PROXYABLE:
        body["proxied"] = bool(payload.get("proxied"))
    if rtype in ("MX", "SRV") and payload.get("priority") is not None:
        body["priority"] = int(payload["priority"])
    comment = payload.get("comment")
    if comment:
        body["comment"] = str(comment)[:100]
    return body


async def create_record(zone_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    data = await _request("POST", f"/zones/{zone_id}/dns_records",
                          json_body=_build_payload(payload))
    return _record(data.get("result") or {})


async def update_record(zone_id: str, record_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    data = await _request("PUT", f"/zones/{zone_id}/dns_records/{record_id}",
                          json_body=_build_payload(payload))
    return _record(data.get("result") or {})


async def delete_record(zone_id: str, record_id: str) -> None:
    await _request("DELETE", f"/zones/{zone_id}/dns_records/{record_id}")
