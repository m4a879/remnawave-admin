"""Cloudflare Registrar — домены и даты продления (Bearer-токен).

База: https://api.cloudflare.com/client/v4
- аккаунт: GET /accounts -> первый доступный id (если не задан вручную)
- домены:  GET /accounts/{id}/registrar/domains -> result[]
Баланса у Registrar API нет (balance=None). Цену продления API тоже не отдаёт.
Токен: My Profile → API Tokens → права Account · Registrar Domains:Read.
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.finance.adapters.base import (
    DEFAULT_TIMEOUT, AdapterError, AdapterField, HosterAdapter, Service, SyncResult,
    register_adapter,
)

logger = logging.getLogger(__name__)

_BASE = "https://api.cloudflare.com/client/v4"


@register_adapter
class CloudflareAdapter(HosterAdapter):
    slug = "cloudflare"
    title = "Cloudflare (домены)"
    description = "Cloudflare Registrar: домены и даты продления. Токен с правом Registrar Domains:Read."
    needs_base_url = False
    fields = [
        AdapterField("token", "API-токен", type="password",
                     help="My Profile → API Tokens → права Account · Registrar Domains:Read."),
        AdapterField("account_id", "ID аккаунта", required=False,
                     help="Если аккаунтов несколько; иначе берётся первый доступный."),
    ]

    async def fetch(self, base_url: Optional[str], credentials: Dict[str, str]) -> SyncResult:
        token = (credentials.get("token") or "").strip()
        if not token:
            raise AdapterError("Не заполнен API-токен")
        acc = (credentials.get("account_id") or "").strip()
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=headers,
                                     follow_redirects=True) as client:
            if not acc:
                acc = await self._account_id(client)
            services = await self._domains(client, acc)
        return SyncResult(balance=None, currency="USD", services=services)

    async def _get(self, client: httpx.AsyncClient, path: str) -> Dict[str, Any]:
        try:
            resp = await client.get(f"{_BASE}{path}")
        except httpx.HTTPError as e:
            raise AdapterError(f"Сеть/HTTP ({path}): {e}")
        if resp.status_code in (401, 403):
            raise AdapterError("Ошибка авторизации: токен Cloudflare отклонён (нужно право Registrar)")
        try:
            data = resp.json()
        except ValueError:
            raise AdapterError(f"Некорректный ответ Cloudflare ({path})")
        if isinstance(data, dict) and data.get("success") is False:
            errs = data.get("errors") or []
            msg = errs[0].get("message") if errs and isinstance(errs[0], dict) else f"HTTP {resp.status_code}"
            raise AdapterError(f"Cloudflare: {msg}")
        if resp.status_code >= 400:
            raise AdapterError(f"Cloudflare HTTP {resp.status_code} ({path})")
        return data if isinstance(data, dict) else {}

    async def _account_id(self, client: httpx.AsyncClient) -> str:
        data = await self._get(client, "/accounts?per_page=5")
        res = data.get("result")
        if isinstance(res, list) and res and isinstance(res[0], dict) and res[0].get("id"):
            return str(res[0]["id"])
        raise AdapterError("Не удалось определить аккаунт Cloudflare — укажи ID аккаунта вручную")

    async def _domains(self, client: httpx.AsyncClient, acc: str) -> List[Service]:
        out: List[Service] = []
        page: Optional[int] = 1
        while page and len(out) < 500:
            data = await self._get(
                client, f"/accounts/{acc}/registrar/domains?per_page=50&page={page}")
            for d in (data.get("result") or []):
                if not isinstance(d, dict):
                    continue
                out.append(Service(
                    name=str(d.get("name") or "?"),
                    status=str(d.get("last_known_status") or "").lower() or None,
                    price=None,
                    currency=None,
                    period="yearly",
                    next_due_at=_date(d.get("expires_at")),
                    external_id=str(d.get("id") or d.get("name") or ""),
                    specs=("автопродление" if d.get("auto_renew") else None),
                    ips=None,
                ))
            info = data.get("result_info") or {}
            total = info.get("total_pages")
            page = (page + 1) if (isinstance(total, int) and page < total) else None
        return out


def _date(v: Any) -> Optional[str]:
    """Из ISO datetime/'YYYY-MM-DD ...' взять дату YYYY-MM-DD."""
    if not v:
        return None
    head = str(v).strip()[:10]
    return head if len(head) == 10 and head[4:5] == "-" and head[7:8] == "-" else None
