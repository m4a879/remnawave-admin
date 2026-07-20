"""Hetzner Cloud — публичный API (Bearer-токен проекта).

База: https://api.hetzner.cloud/v1
- серверы: GET /servers?page&per_page -> servers[], meta.pagination.next_page

У Hetzner Cloud НЕТ эндпоинта баланса аккаунта (тарификация помесячно
постфактум), поэтому balance=None, currency=EUR. Цена сервера — из
server_type.prices по локации сервера (price_monthly.gross, EUR).
Токен: Cloud Console → проект → Security → API Tokens (достаточно Read).
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.finance.adapters.base import (
    DEFAULT_TIMEOUT, AdapterError, AdapterField, HosterAdapter, Service, SyncResult,
    extract_ips, register_adapter,
)

logger = logging.getLogger(__name__)

_BASE = "https://api.hetzner.cloud/v1"
_MAX_SERVERS = 200


@register_adapter
class HetznerAdapter(HosterAdapter):
    slug = "hetzner"
    title = "Hetzner Cloud"
    description = "Hetzner Cloud API (Read-токен проекта). Баланса в API нет — только серверы и их цены."
    needs_base_url = False
    fields = [
        AdapterField("token", "API-токен (Read)", type="password",
                     help="Cloud Console → проект → Security → API Tokens → Read."),
    ]

    async def fetch(self, base_url: Optional[str], credentials: Dict[str, str]) -> SyncResult:
        token = (credentials.get("token") or "").strip()
        if not token:
            raise AdapterError("Не заполнен API-токен")
        headers = {"Authorization": f"Bearer {token}"}
        services: List[Service] = []
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=headers,
                                     follow_redirects=True) as client:
            page: Optional[int] = 1
            while page and len(services) < _MAX_SERVERS:
                data = await self._get(client, f"/servers?page={page}&per_page=50")
                for s in (data.get("servers") or []):
                    if isinstance(s, dict):
                        services.append(_server(s))
                nxt = (((data.get("meta") or {}).get("pagination") or {}).get("next_page"))
                page = nxt if isinstance(nxt, int) else None
        return SyncResult(balance=None, currency="EUR", services=services)

    async def _get(self, client: httpx.AsyncClient, path: str) -> Any:
        try:
            resp = await client.get(f"{_BASE}{path}")
        except httpx.HTTPError as e:
            raise AdapterError(f"Сеть/HTTP ({path}): {e}")
        if resp.status_code in (401, 403):
            raise AdapterError("Ошибка авторизации: токен Hetzner отклонён")
        if resp.status_code >= 400:
            raise AdapterError(f"Hetzner HTTP {resp.status_code} ({path})")
        try:
            return resp.json()
        except ValueError:
            raise AdapterError(f"Некорректный ответ Hetzner ({path})")


def _server(s: Dict[str, Any]) -> Service:
    st = s.get("server_type") or {}
    dc = s.get("datacenter") or {}
    loc = dc.get("location") or {}
    loc_name = loc.get("name")

    price = None
    for p in (st.get("prices") or []):
        if isinstance(p, dict) and p.get("location") == loc_name:
            gross = (p.get("price_monthly") or {}).get("gross")
            try:
                price = round(float(gross), 2)
            except (TypeError, ValueError):
                price = None
            break

    ipv4 = ((s.get("public_net") or {}).get("ipv4") or {}).get("ip")

    specs: List[str] = []
    if st.get("cores"):
        specs.append(f"{st['cores']} vCPU")
    if st.get("memory"):
        specs.append(f"{st['memory']} GB")
    if st.get("disk"):
        specs.append(f"{st['disk']} GB")
    city = loc.get("city") or loc.get("country")
    if city:
        specs.append(str(city))

    return Service(
        name=str(s.get("name") or f"#{s.get('id')}"),
        status=str(s.get("status") or "").lower() or None,
        price=price,
        currency="EUR" if price is not None else None,
        period="monthly" if price is not None else None,
        next_due_at=None,  # у Hetzner нет per-server даты продления
        external_id=str(s.get("id")) if s.get("id") is not None else None,
        specs=" · ".join(specs)[:200] or None,
        ips=([ipv4] if ipv4 else None) or extract_ips(s.get("public_net")) or None,
    )
