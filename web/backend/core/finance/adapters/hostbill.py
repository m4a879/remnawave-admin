"""HostBill — self-hosted биллинг-платформа (JWT-логин email+пароль).

База: адрес инстанса (needs_base_url). HTTP 200 даже при ошибке ({"error": [...]}).
- логин:   POST {base}/login {username,password} -> {token|access_token}
- баланс:  GET  {base}/balance  -> details.acc_credit | details.acc_balance
- услуги:  GET  {base}/service  -> services[]
Поля услуг у разных инстансов разнятся — берём по типовым именам (best-effort).
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.finance.adapters.base import (
    DEFAULT_TIMEOUT, AdapterError, AdapterField, HosterAdapter, Service, SyncResult,
    extract_ips, register_adapter,
)

logger = logging.getLogger(__name__)


def _endpoint(base_url: Optional[str]) -> str:
    b = (base_url or "").strip().rstrip("/")
    if not b:
        raise AdapterError("Не указан адрес HostBill (base_url)")
    return b


@register_adapter
class HostbillAdapter(HosterAdapter):
    slug = "hostbill"
    title = "HostBill"
    description = "HostBill (self-hosted): баланс и услуги. Адрес инстанса + email/пароль."
    needs_base_url = True
    fields = [
        AdapterField("username", "Email / логин"),
        AdapterField("password", "Пароль", type="password"),
    ]

    async def fetch(self, base_url: Optional[str], credentials: Dict[str, str]) -> SyncResult:
        base = _endpoint(base_url)
        user = (credentials.get("username") or "").strip()
        pwd = (credentials.get("password") or "").strip()
        if not (user and pwd):
            raise AdapterError("Заполни email/логин и пароль")
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
            token = await self._login(client, base, user, pwd)
            balance, currency = await self._balance(client, base, token)
            services = await self._services(client, base, token, currency)
        return SyncResult(balance=balance, currency=currency, services=services)

    async def _login(self, client: httpx.AsyncClient, base: str, user: str, pwd: str) -> str:
        try:
            resp = await client.post(f"{base}/login", json={"username": user, "password": pwd})
            data = resp.json()
        except httpx.HTTPError as e:
            raise AdapterError(f"HostBill: сеть/HTTP при логине ({e})")
        except ValueError:
            raise AdapterError("HostBill: некорректный ответ при логине")
        if isinstance(data, dict) and data.get("error"):
            raise AdapterError("HostBill: неверный логин или пароль")
        token = None
        if isinstance(data, dict):
            token = data.get("token") or data.get("access_token")
            if not token and isinstance(data.get("data"), dict):
                token = data["data"].get("token")
        if not token:
            raise AdapterError("HostBill: не получен токен")
        return str(token)

    async def _get(self, client: httpx.AsyncClient, base: str, path: str, token: str) -> Any:
        try:
            resp = await client.get(f"{base}/{path}", headers={"Authorization": f"Bearer {token}"})
            data = resp.json()
        except httpx.HTTPError as e:
            raise AdapterError(f"HostBill: сеть/HTTP ({path}): {e}")
        except ValueError:
            raise AdapterError(f"HostBill: некорректный ответ ({path})")
        if isinstance(data, dict) and data.get("error"):
            raise AdapterError(f"HostBill: {path} — {data.get('error')}")
        return data

    async def _balance(self, client: httpx.AsyncClient, base: str, token: str):
        data = await self._get(client, base, "balance", token)
        det = data.get("details") if isinstance(data, dict) else None
        if not isinstance(det, dict):
            det = data if isinstance(data, dict) else {}
        v = det.get("acc_credit")
        if v in (None, ""):
            v = det.get("acc_balance")
        cur = det.get("currency") or None
        try:
            bal = round(float(v), 2) if v not in (None, "") else None
        except (TypeError, ValueError):
            bal = None
        return bal, (str(cur).upper() if cur else None)

    async def _services(self, client, base, token, currency) -> List[Service]:
        try:
            data = await self._get(client, base, "service", token)
        except AdapterError as e:
            logger.info("HostBill services недоступны: %s", e)
            return []
        rows = data.get("services") if isinstance(data, dict) else (data if isinstance(data, list) else [])
        out: List[Service] = []
        for s in (rows or [])[:100]:
            if not isinstance(s, dict):
                continue
            price = _num(s.get("total") or s.get("recurring") or s.get("amount")
                         or s.get("price") or s.get("firstpaymentamount"))
            out.append(Service(
                name=str(s.get("name") or s.get("domain") or s.get("hostname") or f"#{s.get('id')}"),
                status=str(s.get("status") or "").lower() or None,
                price=price,
                currency=currency if price is not None else None,
                period=_cycle(s.get("billingcycle") or s.get("cycle") or s.get("period")),
                next_due_at=_date(s.get("nextduedate") or s.get("next_due")
                                  or s.get("expiredate") or s.get("duedate")),
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


def _cycle(v: Any) -> Optional[str]:
    s = str(v or "").strip().lower()
    if s in ("monthly", "month", "1"):
        return "monthly"
    if s in ("annually", "yearly", "annual", "year", "12"):
        return "yearly"
    return s or None


def _date(v: Any) -> Optional[str]:
    if not v:
        return None
    head = str(v).strip()[:10]
    return head if len(head) == 10 and head[4:5] == "-" and head[7:8] == "-" else None
