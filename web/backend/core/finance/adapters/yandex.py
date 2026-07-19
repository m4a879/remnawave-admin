"""Yandex Cloud — баланс биллинг-аккаунта (авторизованный ключ сервисного аккаунта).

Поток:
1. Подписываем JWT (PS256) приватным ключом сервисного аккаунта (kid = id ключа)
2. POST https://iam.api.cloud.yandex.net/iam/v1/tokens {jwt} -> iamToken (~55 мин)
3. GET  https://billing.api.cloud.yandex.net/billing/v1/billingAccounts (Bearer)
   -> активный аккаунт: balance / currency

Инстансы (Compute) требуют перебор облаков/папок — отдельный заход (services=[]).
Ключ: консоль YC → сервисный аккаунт (роль billing.accounts.viewer) →
создать авторизованный ключ → скачать JSON и вставить целиком.
"""
import json
import logging
import time
from typing import Any, Dict, Optional

import httpx
from jose import jwt as jose_jwt

from web.backend.core.finance.adapters.base import (
    DEFAULT_TIMEOUT, AdapterError, AdapterField, HosterAdapter, SyncResult,
    register_adapter,
)

logger = logging.getLogger(__name__)

_IAM = "https://iam.api.cloud.yandex.net/iam/v1/tokens"
_BILLING = "https://billing.api.cloud.yandex.net/billing/v1"


@register_adapter
class YandexAdapter(HosterAdapter):
    slug = "yandex"
    title = "Yandex Cloud"
    description = ("Yandex Cloud: баланс биллинг-аккаунта. Авторизованный ключ сервисного "
                  "аккаунта (JSON) с ролью billing.accounts.viewer.")
    needs_base_url = False
    fields = [
        AdapterField("authorized_key", "Авторизованный ключ (JSON)", type="password",
                     help="Консоль YC → сервисный аккаунт → создать авторизованный ключ → "
                          "скачать JSON, вставить целиком."),
    ]

    async def fetch(self, base_url: Optional[str], credentials: Dict[str, str]) -> SyncResult:
        raw = (credentials.get("authorized_key") or "").strip()
        if not raw:
            raise AdapterError("Не заполнен авторизованный ключ")
        try:
            key = json.loads(raw)
        except ValueError:
            raise AdapterError("Ключ должен быть JSON (скачанный из консоли YC)")
        kid = key.get("id")
        sa = key.get("service_account_id")
        pem = key.get("private_key")
        if not (kid and sa and pem):
            raise AdapterError("В ключе нет id / service_account_id / private_key")

        token = await self._iam_token(str(kid), str(sa), str(pem))
        balance, currency = await self._balance(token)
        return SyncResult(balance=balance, currency=currency, services=[])

    async def _iam_token(self, kid: str, sa: str, pem: str) -> str:
        now = int(time.time())
        payload = {"iss": sa, "aud": _IAM, "iat": now, "exp": now + 3600}
        try:
            signed = jose_jwt.encode(payload, pem, algorithm="PS256", headers={"kid": kid})
        except Exception as e:  # noqa: BLE001 — любая ошибка подписи = плохой ключ
            raise AdapterError(f"Не удалось подписать JWT ключом: {e}")
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
                resp = await client.post(_IAM, json={"jwt": signed})
        except httpx.HTTPError as e:
            raise AdapterError(f"Сеть/HTTP (IAM): {e}")
        if resp.status_code >= 400:
            raise AdapterError(f"Yandex IAM отклонил ключ (HTTP {resp.status_code})")
        try:
            tok = resp.json().get("iamToken")
        except ValueError:
            raise AdapterError("Некорректный ответ IAM")
        if not tok:
            raise AdapterError("IAM не вернул токен")
        return str(tok)

    async def _balance(self, token: str):
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=headers,
                                         follow_redirects=True) as client:
                resp = await client.get(f"{_BILLING}/billingAccounts")
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise AdapterError(f"Сеть/HTTP (billing): {e}")
        except ValueError:
            raise AdapterError("Некорректный ответ billing")
        accounts = data.get("billingAccounts") if isinstance(data, dict) else None
        if not accounts:
            return None, "RUB"
        acc = next((a for a in accounts if isinstance(a, dict) and a.get("active")), accounts[0])
        if not isinstance(acc, dict):
            return None, "RUB"
        v = acc.get("balance")
        cur = acc.get("currency") or "RUB"
        try:
            bal = round(float(v), 2) if v is not None else None
        except (TypeError, ValueError):
            bal = None
        return bal, str(cur).upper()
