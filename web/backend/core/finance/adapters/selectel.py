"""Selectel — баланс аккаунта по статическому API-ключу (X-Token).

Статический ключ (панель → Аккаунт → Доступ → Ключи API) даёт полный доступ,
кроме OpenStack; время жизни бессрочно. Проще прежнего Keystone-потока и
реально работает.

- баланс: GET https://api.selectel.ru/v3/balances (X-Token)
          -> data.billings[0].final_sum (копейки) / data.settings.currency
Услуги (облачные серверы) живут в OpenStack, статическому ключу недоступны
(services=[]).
"""
import logging
from typing import Dict, Optional

import httpx

from web.backend.core.finance.adapters.base import (
    DEFAULT_TIMEOUT, AdapterError, AdapterField, HosterAdapter, SyncResult,
    register_adapter,
)

logger = logging.getLogger(__name__)

_API = "https://api.selectel.ru"


@register_adapter
class SelectelAdapter(HosterAdapter):
    slug = "selectel"
    title = "Selectel"
    description = ("Selectel: баланс аккаунта по статическому API-ключу (X-Token). "
                  "Ключ: Аккаунт → Доступ → Ключи API.")
    needs_base_url = False
    fields = [
        AdapterField("token", "API-ключ (X-Token)", type="password",
                     help="Панель Selectel → Аккаунт → Доступ → Ключи API → создать статический ключ."),
    ]

    async def fetch(self, base_url: Optional[str], credentials: Dict[str, str]) -> SyncResult:
        token = (credentials.get("token") or "").strip()
        if not token:
            raise AdapterError("Не заполнен API-ключ")
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers={"X-Token": token},
                                         follow_redirects=True) as client:
                resp = await client.get(f"{_API}/v3/balances")
        except httpx.HTTPError as e:
            raise AdapterError(f"Сеть/HTTP (balances): {e}")
        if resp.status_code in (401, 403):
            raise AdapterError("Ошибка авторизации: ключ Selectel отклонён")
        if resp.status_code >= 400:
            raise AdapterError(f"Selectel HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError:
            raise AdapterError("Некорректный ответ Selectel (balances)")

        d = data.get("data") if isinstance(data, dict) else None
        if not isinstance(d, dict):
            return SyncResult(balance=None, currency="RUB", services=[])
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
        return SyncResult(balance=balance, currency=currency, services=[])
