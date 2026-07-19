"""Aeza — клиентский API (ключ в заголовке X-API-KEY).

База: https://my.aeza.net/api/v2
- аккаунт: GET /accounts/me -> balance (в копейках) / currency
- сервисы: GET /services   -> items[] (пропускаем status == deleted)

Деньги Aeza — в минорных единицах (копейки/центы), делим на 100. Валюта у
сервисов не приходит — проставляем из валюты аккаунта (Aeza одновалютна).
Ключ: панель my.aeza.net -> раздел API.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.finance.adapters.base import (
    DEFAULT_TIMEOUT, AdapterError, AdapterField, HosterAdapter, Service, SyncResult,
    extract_ips, register_adapter,
)

logger = logging.getLogger(__name__)

_BASE = "https://my.aeza.net/api/v2"


@register_adapter
class AezaAdapter(HosterAdapter):
    slug = "aeza"
    title = "Aeza"
    description = "Клиентский API Aeza (my.aeza.net). Ключ: панель → раздел API → создать ключ."
    needs_base_url = False
    fields = [
        AdapterField("api_key", "API-ключ", type="password",
                     help="Панель my.aeza.net → раздел API → создать ключ."),
    ]

    async def fetch(self, base_url: Optional[str], credentials: Dict[str, str]) -> SyncResult:
        key = (credentials.get("api_key") or "").strip()
        if not key:
            raise AdapterError("Не заполнен API-ключ")
        headers = {"X-API-KEY": key}
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=headers,
                                     follow_redirects=True) as client:
            balance, currency = await self._account(client)
            services = await self._services(client, currency)
        return SyncResult(balance=balance, currency=currency, services=services)

    async def _get(self, client: httpx.AsyncClient, path: str) -> Any:
        try:
            resp = await client.get(f"{_BASE}{path}")
        except httpx.HTTPError as e:
            raise AdapterError(f"Сеть/HTTP ({path}): {e}")
        if resp.status_code in (401, 403):
            raise AdapterError("Ошибка авторизации: ключ Aeza отклонён")
        if resp.status_code >= 400:
            raise AdapterError(f"Aeza HTTP {resp.status_code} ({path})")
        try:
            return resp.json()
        except ValueError:
            raise AdapterError(f"Некорректный ответ Aeza ({path})")

    @staticmethod
    def _payload(data: Any) -> Any:
        """Aeza оборачивает полезную нагрузку в объект data — снимаем обёртку."""
        if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
            return data["data"]
        return data

    async def _account(self, client: httpx.AsyncClient):
        data = self._payload(await self._get(client, "/accounts/me"))
        if not isinstance(data, dict):
            return None, None
        cur = data.get("currency")
        return _to_major(data.get("balance")), (str(cur).upper() if cur else None)

    async def _services(self, client: httpx.AsyncClient, currency: Optional[str]) -> List[Service]:
        try:
            data = self._payload(await self._get(client, "/services"))
        except AdapterError as e:
            logger.info("Aeza services недоступны: %s", e)
            return []
        if isinstance(data, dict):
            items = data.get("items") or data.get("services") or []
        else:
            items = data if isinstance(data, list) else []
        out: List[Service] = []
        for s in items[:100]:
            if not isinstance(s, dict):
                continue
            if str(s.get("status") or "").lower() == "deleted":
                continue
            out.append(Service(
                name=str(s.get("name") or s.get("productName") or f"#{s.get('id')}"),
                status=str(s.get("status") or "").lower() or None,
                price=_to_major(s.get("price")),
                currency=currency,
                period=_norm_term(s.get("paymentTerm")),
                next_due_at=_iso(s.get("expiresAt") or s.get("expireAt")),
                external_id=str(s.get("id")) if s.get("id") is not None else None,
                specs=str(s.get("locationCode") or "") or None,
                ips=([s["ip"]] if s.get("ip") else None) or extract_ips(s) or None,
            ))
        return out


def _to_major(v: Any) -> Optional[float]:
    """Минорные единицы (копейки) -> основные."""
    if v in (None, ""):
        return None
    try:
        return round(float(v) / 100, 2)
    except (TypeError, ValueError):
        return None


def _norm_term(v: Any) -> Optional[str]:
    s = str(v or "").strip().lower()
    if s in ("month", "monthly", "1m", "30d"):
        return "monthly"
    if s in ("year", "yearly", "annual", "annually", "12m"):
        return "yearly"
    return s or None


def _iso(v: Any) -> Optional[str]:
    """ISO-строку/дату или unix-таймстамп (сек/мс) -> ISO date (YYYY-MM-DD)."""
    if v in (None, ""):
        return None
    s = str(v).strip()
    if "T" in s:
        d = s.split("T")[0]
        return d if len(d) == 10 and d[4:5] == "-" else None
    if len(s) >= 10 and s[4:5] == "-":
        return s[:10]
    try:
        n = int(float(s))
    except (TypeError, ValueError):
        return None
    if n > 10_000_000_000:  # миллисекунды
        n //= 1000
    if n <= 0:
        return None
    return datetime.fromtimestamp(n, tz=timezone.utc).date().isoformat()
