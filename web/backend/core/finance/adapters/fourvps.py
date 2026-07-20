"""4VPS.su — публичный API (Bearer-ключ + panel_id).

База: https://4vps.su/api
- баланс:  GET /userBalance?panel_id=  -> data.userBalance (RUB)
- серверы: GET /myservers?panel_id=    -> data.serverlist[] (price, expired unix)
Логические ошибки приходят как HTTP 200 + {"error": true, "data": "<текст>"}.
Ключ: панель 4VPS → API.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.finance.adapters.base import (
    DEFAULT_TIMEOUT, AdapterError, AdapterField, HosterAdapter, Service, SyncResult,
    extract_ips, register_adapter,
)

logger = logging.getLogger(__name__)

_BASE = "https://4vps.su/api"


@register_adapter
class FourVpsAdapter(HosterAdapter):
    slug = "4vps"
    title = "4VPS"
    description = "4VPS.su: баланс и серверы (API-ключ, Bearer)."
    needs_base_url = False
    fields = [
        AdapterField("token", "API-ключ", type="password", help="Панель 4VPS → API."),
        AdapterField("panel_id", "panel_id", required=False,
                     help="Обычно 1 (по умолчанию)."),
    ]

    async def fetch(self, base_url: Optional[str], credentials: Dict[str, str]) -> SyncResult:
        token = (credentials.get("token") or "").strip()
        if not token:
            raise AdapterError("Не заполнен API-ключ")
        panel_id = (credentials.get("panel_id") or "1").strip() or "1"
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=headers,
                                     follow_redirects=True) as client:
            balance = await self._balance(client, panel_id)
            services = await self._servers(client, panel_id)
        return SyncResult(balance=balance, currency="RUB", services=services)

    async def _get(self, client: httpx.AsyncClient, path: str, panel_id: str) -> Any:
        try:
            resp = await client.get(f"{_BASE}{path}", params={"panel_id": panel_id})
        except httpx.HTTPError as e:
            raise AdapterError(f"Сеть/HTTP ({path}): {e}")
        if resp.status_code in (401, 403):
            raise AdapterError("Ошибка авторизации: ключ 4VPS отклонён")
        try:
            data = resp.json()
        except ValueError:
            raise AdapterError(f"Некорректный ответ 4VPS ({path})")
        if isinstance(data, dict) and data.get("error"):
            raise AdapterError(f"4VPS: {data.get('data') or 'ошибка API'}")
        return data.get("data") if isinstance(data, dict) else data

    async def _balance(self, client: httpx.AsyncClient, panel_id: str) -> Optional[float]:
        d = await self._get(client, "/userBalance", panel_id)
        v = d.get("userBalance") if isinstance(d, dict) else d
        try:
            return round(float(v), 2) if v is not None else None
        except (TypeError, ValueError):
            return None

    async def _servers(self, client: httpx.AsyncClient, panel_id: str) -> List[Service]:
        try:
            d = await self._get(client, "/myservers", panel_id)
        except AdapterError as e:
            logger.info("4VPS servers недоступны: %s", e)
            return []
        rows = d.get("serverlist") if isinstance(d, dict) else (d if isinstance(d, list) else [])
        out: List[Service] = []
        for s in (rows or [])[:100]:
            if not isinstance(s, dict) or s.get("deleted"):
                continue
            price = _num(s.get("price"))
            out.append(Service(
                name=str(s.get("name") or s.get("hostname") or s.get("domain") or f"#{s.get('id')}"),
                status=str(s.get("status") or "").lower() or None,
                price=price,
                currency="RUB" if price is not None else None,
                period="monthly" if price is not None else None,
                next_due_at=_unix_date(s.get("expired")),
                external_id=str(s.get("id")) if s.get("id") else None,
                specs=None,
                ips=extract_ips(s) or None,
            ))
        return out


def _num(v: Any) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def _unix_date(v: Any) -> Optional[str]:
    if v in (None, "", 0, "0"):
        return None
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    if n > 10_000_000_000:
        n //= 1000
    return datetime.fromtimestamp(n, tz=timezone.utc).date().isoformat()
