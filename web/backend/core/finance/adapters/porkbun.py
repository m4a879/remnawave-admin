"""Porkbun — регистратор доменов (apikey + secretapikey в теле JSON).

База: https://api.porkbun.com/api/json/v3
- баланс: POST /account/balance   -> balance (best-effort; у части аккаунтов нет)
- домены: POST /domain/listAll    -> domains[] (пагинация start, до 1000/страница)
Все ответы: {status: "SUCCESS"|"ERROR", ...}. Ключи: Account → API Access.
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.finance.adapters.base import (
    DEFAULT_TIMEOUT, AdapterError, AdapterField, HosterAdapter, Service, SyncResult,
    register_adapter,
)

logger = logging.getLogger(__name__)

_BASE = "https://api.porkbun.com/api/json/v3"


@register_adapter
class PorkbunAdapter(HosterAdapter):
    slug = "porkbun"
    title = "Porkbun (домены)"
    description = "Porkbun: домены и даты истечения. Ключи: Account → API Access (pk1_/sk1_)."
    needs_base_url = False
    fields = [
        AdapterField("apikey", "API-ключ", help="Porkbun → Account → API Access (pk1_…)."),
        AdapterField("secretapikey", "Secret API-ключ", type="password",
                     help="Секретный ключ (sk1_…)."),
    ]

    async def fetch(self, base_url: Optional[str], credentials: Dict[str, str]) -> SyncResult:
        ak = (credentials.get("apikey") or "").strip()
        sk = (credentials.get("secretapikey") or "").strip()
        if not (ak and sk):
            raise AdapterError("Заполни API-ключ и секретный ключ")
        auth = {"apikey": ak, "secretapikey": sk}
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
            balance = await self._balance(client, auth)
            services = await self._domains(client, auth)
        return SyncResult(balance=balance, currency="USD", services=services)

    async def _post(self, client: httpx.AsyncClient, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        try:
            resp = await client.post(f"{_BASE}{path}", json=body)
        except httpx.HTTPError as e:
            raise AdapterError(f"Сеть/HTTP ({path}): {e}")
        try:
            data = resp.json()
        except ValueError:
            raise AdapterError(f"Некорректный ответ Porkbun ({path})")
        if isinstance(data, dict) and str(data.get("status")).upper() == "ERROR":
            raise AdapterError(f"Porkbun: {data.get('message') or 'ошибка'}")
        if resp.status_code >= 400:
            raise AdapterError(f"Porkbun HTTP {resp.status_code} ({path})")
        return data if isinstance(data, dict) else {}

    async def _balance(self, client: httpx.AsyncClient, auth: Dict[str, str]) -> Optional[float]:
        try:
            data = await self._post(client, "/account/balance", dict(auth))
        except AdapterError:
            return None  # у многих аккаунтов баланса нет — не критично
        v = data.get("balance")
        try:
            return round(float(v), 2) if v is not None else None
        except (TypeError, ValueError):
            return None

    async def _domains(self, client: httpx.AsyncClient, auth: Dict[str, str]) -> List[Service]:
        out: List[Service] = []
        start = 0
        for _ in range(10):  # cap: до 10k доменов
            data = await self._post(client, "/domain/listAll", {**auth, "start": str(start)})
            domains = data.get("domains")
            if not isinstance(domains, list) or not domains:
                break
            for d in domains:
                if not isinstance(d, dict):
                    continue
                out.append(Service(
                    name=str(d.get("domain") or "?"),
                    status=str(d.get("status") or "").lower() or None,
                    price=None,
                    currency=None,
                    period="yearly",
                    next_due_at=_date(d.get("expireDate")),
                    external_id=str(d.get("domain") or ""),
                    specs=("автопродление" if str(d.get("autoRenew")) in ("1", "true", "True") else None),
                    ips=None,
                ))
            if len(domains) < 1000:
                break
            start += len(domains)
        return out


def _date(v: Any) -> Optional[str]:
    if not v:
        return None
    head = str(v).strip()[:10]
    return head if len(head) == 10 and head[4:5] == "-" and head[7:8] == "-" else None
