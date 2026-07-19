"""VDSina — публичный API (токен в заголовке Authorization).

База: https://userapi.vdsina.ru (RUB; .com = USD)
- баланс:  GET /v1/account.balance -> data.real
- серверы: GET /v1/server          -> data[] (server-plan.cost — цена)
Все ответы обёрнуты конвертом {status, data}; status=="error" -> ошибка.
Токен: панель VDSina → Настройки → API-ключ.
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.finance.adapters.base import (
    DEFAULT_TIMEOUT, AdapterError, AdapterField, HosterAdapter, Service, SyncResult,
    extract_ips, register_adapter,
)

logger = logging.getLogger(__name__)

_BASE = "https://userapi.vdsina.ru"


@register_adapter
class VdsinaAdapter(HosterAdapter):
    slug = "vdsina"
    title = "VDSina"
    description = "VDSina API (userapi.vdsina.ru, RUB). Токен: панель → Настройки → API-ключ."
    needs_base_url = False
    fields = [
        AdapterField("token", "API-токен", type="password",
                     help="Панель VDSina → Настройки → API-ключ."),
    ]

    async def fetch(self, base_url: Optional[str], credentials: Dict[str, str]) -> SyncResult:
        token = (credentials.get("token") or "").strip()
        if not token:
            raise AdapterError("Не заполнен API-токен")
        headers = {"Authorization": token}
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=headers,
                                     follow_redirects=True) as client:
            balance = await self._balance(client)
            services = await self._services(client)
        return SyncResult(balance=balance, currency="RUB", services=services)

    async def _get(self, client: httpx.AsyncClient, path: str) -> Any:
        """Вернуть распакованное data; конверт status=='error' -> AdapterError."""
        try:
            resp = await client.get(f"{_BASE}{path}")
        except httpx.HTTPError as e:
            raise AdapterError(f"Сеть/HTTP ({path}): {e}")
        if resp.status_code in (401, 403):
            raise AdapterError("Ошибка авторизации: токен VDSina отклонён")
        if resp.status_code >= 400:
            raise AdapterError(f"VDSina HTTP {resp.status_code} ({path})")
        try:
            data = resp.json()
        except ValueError:
            raise AdapterError(f"Некорректный ответ VDSina ({path})")
        if isinstance(data, dict) and str(data.get("status")).lower() == "error":
            msg = data.get("data")
            raise AdapterError(f"VDSina: {msg if isinstance(msg, str) else 'ошибка API'}")
        return data.get("data") if isinstance(data, dict) else data

    async def _balance(self, client: httpx.AsyncClient) -> Optional[float]:
        data = await self._get(client, "/v1/account.balance")
        if not isinstance(data, dict):
            return None
        v = data.get("real")
        if v is None:
            v = data.get("amount") or data.get("balance")
        try:
            return round(float(v), 2) if v is not None else None
        except (TypeError, ValueError):
            return None

    async def _services(self, client: httpx.AsyncClient) -> List[Service]:
        try:
            data = await self._get(client, "/v1/server")
        except AdapterError as e:
            logger.info("VDSina servers недоступны: %s", e)
            return []
        rows = data if isinstance(data, list) else []
        out: List[Service] = []
        for s in rows[:100]:
            if not isinstance(s, dict):
                continue
            plan = s.get("server-plan") or s.get("server_plan") or {}
            price = None
            if isinstance(plan, dict) and plan.get("cost") is not None:
                try:
                    price = round(float(plan["cost"]), 2)
                except (TypeError, ValueError):
                    price = None
            out.append(Service(
                name=str(s.get("name") or f"#{s.get('id')}"),
                status=str(s.get("status") or "").lower() or None,
                price=price,
                currency="RUB" if price is not None else None,
                period=_norm_period(plan.get("period")) if isinstance(plan, dict) else None,
                next_due_at=None,
                external_id=str(s.get("id")) if s.get("id") else None,
                specs=(str(plan.get("name")) if isinstance(plan, dict) and plan.get("name") else None),
                ips=extract_ips(s) or None,
            ))
        return out


def _norm_period(v: Any) -> Optional[str]:
    s = str(v or "").strip().lower()
    if s in ("month", "monthly", "1", "30"):
        return "monthly"
    if s in ("year", "yearly", "12"):
        return "yearly"
    return s or None
