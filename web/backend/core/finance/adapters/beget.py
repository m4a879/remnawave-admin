"""Beget — баланс (legacy API) + VPS (Cloud API v1, best-effort).

База: https://api.beget.com
- баланс: GET /api/user/getAccountInfo?login&passwd&output_format=json
          -> answer.result.user_balance (RUB). Обёртки status на двух уровнях,
          HTTP 200 даже при ошибке.
- VPS:    POST /v1/auth {login,password} -> {token} (JWT); затем
          GET /v1/vps/server/list (Bearer). На многих аккаунтах API-пароль ≠
          паролю аккаунта, поэтому неуспех auth не критичен — баланс уже есть.
Пароль — из раздела «API» панели Beget (отдельный пароль для доступа).
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.finance.adapters.base import (
    DEFAULT_TIMEOUT, AdapterError, AdapterField, HosterAdapter, Service, SyncResult,
    extract_ips, register_adapter,
)

logger = logging.getLogger(__name__)

_BASE = "https://api.beget.com"


@register_adapter
class BegetAdapter(HosterAdapter):
    slug = "beget"
    title = "Beget"
    description = "Beget: баланс (legacy) + VPS (Cloud API). Пароль — из раздела «API» панели."
    needs_base_url = False
    fields = [
        AdapterField("login", "Логин Beget", help="Логин аккаунта Beget."),
        AdapterField("passwd", "Пароль API", type="password",
                     help="Панель Beget → раздел «API» → пароль для доступа."),
    ]

    async def fetch(self, base_url: Optional[str], credentials: Dict[str, str]) -> SyncResult:
        login = (credentials.get("login") or "").strip()
        passwd = (credentials.get("passwd") or "").strip()
        if not (login and passwd):
            raise AdapterError("Заполни логин и пароль API")
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
            balance = await self._balance(client, login, passwd)
            services = await self._vps(client, login, passwd)
        return SyncResult(balance=balance, currency="RUB", services=services)

    async def _balance(self, client: httpx.AsyncClient, login: str, passwd: str) -> Optional[float]:
        params = {"login": login, "passwd": passwd, "output_format": "json"}
        try:
            resp = await client.get(f"{_BASE}/api/user/getAccountInfo", params=params)
            data = resp.json()
        except httpx.HTTPError as e:
            raise AdapterError(f"Beget: сеть/HTTP при запросе баланса ({e})")
        except ValueError:
            raise AdapterError("Beget: некорректный ответ при запросе баланса")
        if not isinstance(data, dict) or str(data.get("status")).lower() == "error":
            raise AdapterError(f"Beget: {(isinstance(data, dict) and data.get('error_text')) or 'ошибка запроса'}")
        answer = data.get("answer") or {}
        if str(answer.get("status")).lower() == "error":
            raise AdapterError("Beget: неверный логин или пароль API")
        result = answer.get("result") or {}
        v = result.get("user_balance")
        try:
            return round(float(v), 2) if v is not None else None
        except (TypeError, ValueError):
            return None

    async def _vps(self, client: httpx.AsyncClient, login: str, passwd: str) -> List[Service]:
        try:
            auth = await client.post(f"{_BASE}/v1/auth", json={"login": login, "password": passwd})
            token = (auth.json() or {}).get("token")
        except (httpx.HTTPError, ValueError):
            return []
        if not token:
            logger.info("Beget Cloud auth не дал токен — VPS пропущены (баланс есть)")
            return []
        try:
            resp = await client.get(f"{_BASE}/v1/vps/server/list",
                                    headers={"Authorization": f"Bearer {token}"})
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return []
        rows = None
        if isinstance(data, dict):
            rows = data.get("vps") or data.get("server") or data.get("result")
        if not isinstance(rows, list):
            return []
        out: List[Service] = []
        for s in rows[:100]:
            if not isinstance(s, dict):
                continue
            price = _num(s.get("price_month") or s.get("price"))
            out.append(Service(
                name=str(s.get("display_name") or s.get("hostname") or s.get("name") or f"#{s.get('id')}"),
                status=str(s.get("status") or "").lower() or None,
                price=price,
                currency="RUB" if price is not None else None,
                period="monthly" if price is not None else None,
                next_due_at=None,
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
