"""Timeweb Cloud — публичный REST API (Bearer-токен).

База: https://api.timeweb.cloud
- баланс:  GET /api/v1/account/finances -> finances.balance / finances.currency
- серверы: GET /api/v1/servers -> servers[]
- цены:    GET /api/v1/presets/servers -> server_presets[] (price — МЕСЯЧНАЯ)

Timeweb тарифицирует почасово из баланса, поэтому даты продления у сервера нет:
цену показываем как месячный эквивалент пресета, next_due_at не заполняем.
Токен: панель Timeweb Cloud -> «API и терминал» -> создать токен (JWT).
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.finance.adapters.base import (
    DEFAULT_TIMEOUT, AdapterError, AdapterField, HosterAdapter, Service, SyncResult,
    extract_ips, register_adapter,
)

logger = logging.getLogger(__name__)

_BASE = "https://api.timeweb.cloud"


@register_adapter
class TimewebAdapter(HosterAdapter):
    slug = "timeweb"
    title = "Timeweb Cloud"
    description = "Публичный API Timeweb Cloud. Токен: панель → «API и терминал» → создать токен."
    needs_base_url = False
    fields = [
        AdapterField("token", "API-токен", type="password",
                     help="Панель Timeweb Cloud → «API и терминал» → создать токен (JWT)."),
    ]

    async def fetch(self, base_url: Optional[str], credentials: Dict[str, str]) -> SyncResult:
        token = (credentials.get("token") or "").strip()
        if not token:
            raise AdapterError("Не заполнен API-токен")
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=headers,
                                     follow_redirects=True) as client:
            balance, currency = await self._balance(client)
            services = await self._services(client, currency)
        return SyncResult(balance=balance, currency=currency, services=services)

    async def _get(self, client: httpx.AsyncClient, path: str) -> Any:
        try:
            resp = await client.get(f"{_BASE}{path}")
        except httpx.HTTPError as e:
            raise AdapterError(f"Сеть/HTTP ({path}): {e}")
        if resp.status_code in (401, 403):
            raise AdapterError("Ошибка авторизации: токен Timeweb отклонён")
        if resp.status_code >= 400:
            raise AdapterError(f"Timeweb HTTP {resp.status_code} ({path})")
        try:
            return resp.json()
        except ValueError:
            raise AdapterError(f"Некорректный ответ Timeweb ({path})")

    async def _balance(self, client: httpx.AsyncClient):
        data = await self._get(client, "/api/v1/account/finances")
        fin = data.get("finances") if isinstance(data, dict) else None
        if not isinstance(fin, dict):
            return None, "RUB"
        bal = fin.get("balance")
        try:
            bal = round(float(bal), 2) if bal is not None else None
        except (TypeError, ValueError):
            bal = None
        return bal, str(fin.get("currency") or "RUB").upper()

    async def _services(self, client: httpx.AsyncClient, currency: Optional[str]) -> List[Service]:
        try:
            srv = await self._get(client, "/api/v1/servers")
        except AdapterError as e:
            logger.info("Timeweb servers недоступны: %s", e)
            return []
        presets: Dict[Any, Dict[str, Any]] = {}
        try:
            pres = await self._get(client, "/api/v1/presets/servers")
            for p in (pres.get("server_presets") or []):
                if isinstance(p, dict) and p.get("id") is not None:
                    presets[p["id"]] = p
        except AdapterError:
            pass  # без пресетов просто не будет цены
        out: List[Service] = []
        for s in (srv.get("servers") or [])[:100]:
            if not isinstance(s, dict):
                continue
            preset = presets.get(s.get("preset_id"))
            price = None
            if preset is not None and preset.get("price") is not None:
                try:
                    price = round(float(preset["price"]), 2)
                except (TypeError, ValueError):
                    price = None
            out.append(Service(
                name=str(s.get("name") or f"#{s.get('id')}"),
                status=str(s.get("status") or "").lower() or None,
                price=price,
                currency=currency if price is not None else None,
                period="monthly" if price is not None else None,
                next_due_at=None,  # почасовая тарификация из баланса
                external_id=str(s.get("id")) if s.get("id") is not None else None,
                specs=_specs(s, preset),
                ips=extract_ips(s) or None,
            ))
        return out


def _specs(s: Dict[str, Any], preset: Optional[Dict[str, Any]]) -> Optional[str]:
    parts: List[str] = []
    if s.get("cpu"):
        parts.append(f"{s['cpu']} vCPU")
    if s.get("ram"):
        parts.append(f"{s['ram']} MB")
    loc = s.get("location") or (preset or {}).get("location")
    if loc:
        parts.append(str(loc))
    return " · ".join(parts)[:200] or None
