"""Selectel — баланс аккаунта через сервисного пользователя (Keystone v3).

Поток:
1. POST https://cloud.api.selcloud.ru/identity/v3/auth/tokens (account-scope)
   -> токен в заголовке ОТВЕТА X-Subject-Token
2. GET  https://api.selectel.ru/v3/balances  (X-Auth-Token)
   -> data.billings[0].final_sum (в копейках) / data.settings.currency

Услуги (серверы) у Selectel живут в OpenStack (Nova) и требуют проектного
скоупа + региона из каталога — отдельный заход, пока не реализовано (services=[]).
Креды: номер аккаунта + сервисный пользователь (панель → Управление пользователями).
"""
import logging
from typing import Any, Dict, Optional

import httpx

from web.backend.core.finance.adapters.base import (
    DEFAULT_TIMEOUT, AdapterError, AdapterField, HosterAdapter, SyncResult,
    register_adapter,
)

logger = logging.getLogger(__name__)

_KEYSTONE = "https://cloud.api.selcloud.ru/identity/v3/auth/tokens"
_API = "https://api.selectel.ru"


@register_adapter
class SelectelAdapter(HosterAdapter):
    slug = "selectel"
    title = "Selectel"
    description = ("Selectel: баланс аккаунта через сервисного пользователя (Keystone). "
                   "Услуги/серверы (OpenStack) — в следующем заходе.")
    needs_base_url = False
    fields = [
        AdapterField("account_id", "Номер аккаунта",
                     help="ID аккаунта Selectel (число, напр. 123456)."),
        AdapterField("username", "Сервисный пользователь",
                     help="Панель → Управление пользователями → сервисный пользователь."),
        AdapterField("password", "Пароль", type="password"),
    ]

    async def fetch(self, base_url: Optional[str], credentials: Dict[str, str]) -> SyncResult:
        acc = (credentials.get("account_id") or "").strip()
        user = (credentials.get("username") or "").strip()
        pwd = (credentials.get("password") or "").strip()
        if not (acc and user and pwd):
            raise AdapterError("Заполни номер аккаунта, сервисного пользователя и пароль")
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
            token = await self._token(client, acc, user, pwd)
            balance, currency = await self._balance(client, token)
        return SyncResult(balance=balance, currency=currency, services=[])

    async def _token(self, client: httpx.AsyncClient, acc: str, user: str, pwd: str) -> str:
        body = {"auth": {
            "identity": {"methods": ["password"], "password": {"user": {
                "name": user, "domain": {"name": acc}, "password": pwd,
            }}},
            "scope": {"domain": {"name": acc}},
        }}
        try:
            resp = await client.post(_KEYSTONE, json=body)
        except httpx.HTTPError as e:
            raise AdapterError(f"Сеть/HTTP (Keystone): {e}")
        if resp.status_code in (401, 403):
            raise AdapterError("Ошибка авторизации: неверный аккаунт/пользователь/пароль")
        if resp.status_code >= 400:
            raise AdapterError(f"Selectel Keystone HTTP {resp.status_code}")
        token = resp.headers.get("X-Subject-Token")
        if not token:
            raise AdapterError("Keystone не вернул токен (нет X-Subject-Token)")
        return token

    async def _balance(self, client: httpx.AsyncClient, token: str):
        try:
            resp = await client.get(f"{_API}/v3/balances", headers={"X-Auth-Token": token})
        except httpx.HTTPError as e:
            raise AdapterError(f"Сеть/HTTP (balances): {e}")
        if resp.status_code in (401, 403):
            raise AdapterError("Ошибка авторизации при запросе баланса")
        if resp.status_code >= 400:
            raise AdapterError(f"Selectel balances HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError:
            raise AdapterError("Некорректный ответ Selectel (balances)")

        d = data.get("data") if isinstance(data, dict) else None
        if not isinstance(d, dict):
            return None, "RUB"
        billings = d.get("billings")
        final = None
        if isinstance(billings, list) and billings and isinstance(billings[0], dict):
            final = billings[0].get("final_sum")
        currency = str((d.get("settings") or {}).get("currency") or "RUB").upper()
        balance = None
        if final is not None:
            try:
                balance = round(float(final) / 100, 2)
            except (TypeError, ValueError):
                balance = None
        return balance, currency
