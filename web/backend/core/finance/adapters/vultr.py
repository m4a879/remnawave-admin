"""Vultr — публичный API v2 (Bearer Personal Access Token).

База: https://api.vultr.com/v2
- баланс:  GET /account   -> account.balance (USD)
- инстансы: GET /instances (курсорная пагинация meta.links.next)
- планы:   GET /plans     -> monthly_cost по plan id (цена инстанса)
Токен: Vultr → Account → API → Personal Access Token.
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.finance.adapters.base import (
    DEFAULT_TIMEOUT, AdapterError, AdapterField, HosterAdapter, Service, SyncResult,
    extract_ips, register_adapter,
)

logger = logging.getLogger(__name__)

_BASE = "https://api.vultr.com/v2"
_CUR = "USD"


@register_adapter
class VultrAdapter(HosterAdapter):
    slug = "vultr"
    title = "Vultr"
    description = "Vultr API v2 (Personal Access Token). Токен: Account → API."
    needs_base_url = False
    fields = [
        AdapterField("token", "API-ключ", type="password",
                     help="Vultr → Account → API → Personal Access Token."),
    ]

    async def fetch(self, base_url: Optional[str], credentials: Dict[str, str]) -> SyncResult:
        token = (credentials.get("token") or "").strip()
        if not token:
            raise AdapterError("Не заполнен API-ключ")
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
            raise AdapterError("Ошибка авторизации: ключ Vultr отклонён")
        if resp.status_code >= 400:
            raise AdapterError(f"Vultr HTTP {resp.status_code} ({path})")
        try:
            return resp.json()
        except ValueError:
            raise AdapterError(f"Некорректный ответ Vultr ({path})")

    async def _balance(self, client: httpx.AsyncClient) -> Optional[float]:
        data = await self._get(client, "/account")
        acc = data.get("account") if isinstance(data, dict) else None
        if not isinstance(acc, dict) or acc.get("balance") is None:
            return None
        try:
            return round(float(acc["balance"]), 2)
        except (TypeError, ValueError):
            return None

    async def _services(self, client: httpx.AsyncClient) -> List[Service]:
        plans: Dict[Any, Dict[str, Any]] = {}
        try:
            pd = await self._get(client, "/plans?per_page=500")
            for p in (pd.get("plans") or []):
                if isinstance(p, dict) and p.get("id"):
                    plans[p["id"]] = p
        except AdapterError:
            pass
        out: List[Service] = []
        cursor: Optional[str] = None
        for _ in range(20):  # cap страниц
            path = "/instances?per_page=500" + (f"&cursor={cursor}" if cursor else "")
            data = await self._get(client, path)
            for s in (data.get("instances") or []):
                if not isinstance(s, dict):
                    continue
                plan = plans.get(s.get("plan"))
                price = None
                if plan is not None and plan.get("monthly_cost") is not None:
                    try:
                        price = round(float(plan["monthly_cost"]), 2)
                    except (TypeError, ValueError):
                        price = None
                out.append(Service(
                    name=str(s.get("label") or s.get("main_ip") or f"#{s.get('id')}"),
                    status=str(s.get("status") or "").lower() or None,
                    price=price,
                    currency=_CUR if price is not None else None,
                    period="monthly" if price is not None else None,
                    next_due_at=None,
                    external_id=str(s.get("id")) if s.get("id") else None,
                    specs=_specs(s),
                    ips=extract_ips(s) or None,
                ))
            cursor = (((data.get("meta") or {}).get("links") or {}).get("next")) or None
            if not cursor:
                break
        return out


def _specs(s: Dict[str, Any]) -> Optional[str]:
    parts: List[str] = []
    if s.get("vcpu_count"):
        parts.append(f"{s['vcpu_count']} vCPU")
    if s.get("ram"):
        parts.append(f"{s['ram']} MB")
    if s.get("region"):
        parts.append(str(s["region"]))
    return " · ".join(parts)[:200] or None
