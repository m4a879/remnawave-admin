"""Linode (Akamai) — публичный API v4 (Bearer Personal Access Token).

База: https://api.linode.com/v4
- баланс:  GET /account -> balance (постоплата: положительное = ДОЛГ,
           инвертируем, чтобы кредит был положительным, долг — отрицательным)
- инстансы: GET /linode/instances (пагинация page/pages)
- типы:    GET /linode/types -> цена по type id (region_prices переопределяет
           базовую price.monthly для региона инстанса)
Токен: Cloud Manager → Profile → API Tokens (достаточно Read-only).
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.finance.adapters.base import (
    DEFAULT_TIMEOUT, AdapterError, AdapterField, HosterAdapter, Service, SyncResult,
    extract_ips, register_adapter,
)

logger = logging.getLogger(__name__)

_BASE = "https://api.linode.com/v4"
_CUR = "USD"


@register_adapter
class LinodeAdapter(HosterAdapter):
    slug = "linode"
    title = "Linode"
    description = "Linode/Akamai API v4 (Personal Access Token). Токен: Profile → API Tokens."
    needs_base_url = False
    fields = [
        AdapterField("token", "API-токен", type="password",
                     help="Cloud Manager → Profile → API Tokens (Read-only достаточно)."),
    ]

    async def fetch(self, base_url: Optional[str], credentials: Dict[str, str]) -> SyncResult:
        token = (credentials.get("token") or "").strip()
        if not token:
            raise AdapterError("Не заполнен API-токен")
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=headers,
                                     follow_redirects=True) as client:
            balance = await self._balance(client)
            services = await self._services(client)
        return SyncResult(balance=balance, currency=_CUR, services=services)

    async def _get(self, client: httpx.AsyncClient, path: str) -> Any:
        try:
            resp = await client.get(f"{_BASE}{path}")
        except httpx.HTTPError as e:
            raise AdapterError(f"Сеть/HTTP ({path}): {e}")
        if resp.status_code in (401, 403):
            raise AdapterError("Ошибка авторизации: токен Linode отклонён")
        if resp.status_code >= 400:
            raise AdapterError(f"Linode HTTP {resp.status_code} ({path})")
        try:
            return resp.json()
        except ValueError:
            raise AdapterError(f"Некорректный ответ Linode ({path})")

    async def _balance(self, client: httpx.AsyncClient) -> Optional[float]:
        data = await self._get(client, "/account")
        v = data.get("balance") if isinstance(data, dict) else None
        try:
            return round(-float(v), 2) if v is not None else None
        except (TypeError, ValueError):
            return None

    async def _services(self, client: httpx.AsyncClient) -> List[Service]:
        types: Dict[Any, Dict[str, Any]] = {}
        try:
            td = await self._get(client, "/linode/types")
            for t in (td.get("data") or []):
                if isinstance(t, dict) and t.get("id"):
                    types[t["id"]] = t
        except AdapterError:
            pass
        out: List[Service] = []
        page = 1
        for _ in range(50):  # cap страниц
            data = await self._get(client, f"/linode/instances?page_size=500&page={page}")
            for s in (data.get("data") or []):
                if not isinstance(s, dict):
                    continue
                price = _price(types.get(s.get("type")), s.get("region"))
                ips = [ip for ip in (s.get("ipv4") or []) if isinstance(ip, str)] or extract_ips(s) or None
                out.append(Service(
                    name=str(s.get("label") or f"#{s.get('id')}"),
                    status=str(s.get("status") or "").lower() or None,
                    price=price,
                    currency=_CUR if price is not None else None,
                    period="monthly" if price is not None else None,
                    next_due_at=None,
                    external_id=str(s.get("id")) if s.get("id") else None,
                    specs=_specs(s),
                    ips=ips,
                ))
            pages = data.get("pages") if isinstance(data, dict) else 1
            if not isinstance(pages, int) or page >= pages:
                break
            page += 1
        return out


def _price(t: Optional[Dict[str, Any]], region: Any) -> Optional[float]:
    if not isinstance(t, dict):
        return None
    for rp in (t.get("region_prices") or []):
        if isinstance(rp, dict) and rp.get("id") == region and rp.get("monthly") is not None:
            try:
                return round(float(rp["monthly"]), 2)
            except (TypeError, ValueError):
                pass
    base = (t.get("price") or {}).get("monthly")
    try:
        return round(float(base), 2) if base is not None else None
    except (TypeError, ValueError):
        return None


def _specs(s: Dict[str, Any]) -> Optional[str]:
    sp = s.get("specs") or {}
    parts: List[str] = []
    if sp.get("vcpus"):
        parts.append(f"{sp['vcpus']} vCPU")
    if sp.get("memory"):
        parts.append(f"{sp['memory']} MB")
    if s.get("region"):
        parts.append(str(s["region"]))
    return " · ".join(parts)[:200] or None
