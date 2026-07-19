"""Netlen — публичный API (заголовок X-API-Key).

База: https://api.netlen.com.tr/v1
- баланс:  GET /balance  -> data.balance (USD)
- серверы: GET /servers  -> data[] (amount — месячная цена)
Ответы: {"success": true, "data": ...} либо {"success": false, "error", "code"}.
Ключ: панель Netlen → API.
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

_BASE = "https://api.netlen.com.tr/v1"


@register_adapter
class NetlenAdapter(HosterAdapter):
    slug = "netlen"
    title = "Netlen"
    description = "Netlen: баланс и серверы (X-API-Key, USD)."
    needs_base_url = False
    fields = [
        AdapterField("api_key", "API-ключ", type="password", help="Панель Netlen → API."),
    ]

    async def fetch(self, base_url: Optional[str], credentials: Dict[str, str]) -> SyncResult:
        key = (credentials.get("api_key") or "").strip()
        if not key:
            raise AdapterError("Не заполнен API-ключ")
        headers = {"X-API-Key": key}
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=headers,
                                     follow_redirects=True) as client:
            balance = await self._balance(client)
            services = await self._servers(client)
        return SyncResult(balance=balance, currency="USD", services=services)

    async def _get(self, client: httpx.AsyncClient, path: str) -> Any:
        try:
            resp = await client.get(f"{_BASE}{path}")
        except httpx.HTTPError as e:
            raise AdapterError(f"Сеть/HTTP ({path}): {e}")
        if resp.status_code in (401, 403):
            raise AdapterError("Ошибка авторизации: ключ Netlen отклонён")
        try:
            data = resp.json()
        except ValueError:
            raise AdapterError(f"Некорректный ответ Netlen ({path})")
        if isinstance(data, dict) and data.get("success") is False:
            raise AdapterError(f"Netlen: {data.get('error') or data.get('code') or 'ошибка'}")
        return data.get("data") if isinstance(data, dict) else data

    async def _balance(self, client: httpx.AsyncClient) -> Optional[float]:
        d = await self._get(client, "/balance")
        v = d.get("balance") if isinstance(d, dict) else d
        try:
            return round(float(v), 2) if v is not None else None
        except (TypeError, ValueError):
            return None

    async def _servers(self, client: httpx.AsyncClient) -> List[Service]:
        try:
            d = await self._get(client, "/servers")
        except AdapterError as e:
            logger.info("Netlen servers недоступны: %s", e)
            return []
        if isinstance(d, dict):
            rows = d.get("items") or d.get("servers") or []
        else:
            rows = d if isinstance(d, list) else []
        out: List[Service] = []
        for s in (rows or [])[:100]:
            if not isinstance(s, dict):
                continue
            price = _num(s.get("amount") or s.get("price") or s.get("monthly"))
            out.append(Service(
                name=str(s.get("name") or s.get("hostname") or s.get("label") or f"#{s.get('id')}"),
                status=str(s.get("status") or "").lower() or None,
                price=price,
                currency="USD" if price is not None else None,
                period="monthly" if price is not None else None,
                next_due_at=_any_date(s.get("expires_at") or s.get("due_date") or s.get("expiry")),
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


def _any_date(v: Any) -> Optional[str]:
    if v in (None, ""):
        return None
    s = str(v).strip()
    if "T" in s or (len(s) >= 10 and s[4:5] == "-"):
        return s[:10] if s[4:5] == "-" else s.split("T")[0][:10]
    try:
        n = int(float(s))
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    if n > 10_000_000_000:
        n //= 1000
    return datetime.fromtimestamp(n, tz=timezone.utc).date().isoformat()
