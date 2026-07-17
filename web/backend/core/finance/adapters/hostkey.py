"""Hostkey Invapi — клиентский API (обёртка над WHMCS).

База: https://invapi.hostkey.ru (RU) или .com. Поток:
1. api_key -> сессионный токен (POST auth.php, api_key=...)
2. баланс: POST whmcs.php action=getcredits, token=... -> сумма кредитов
3. услуги: POST whmcs.php action=getclientsproducts (WHMCS) -> продукты с nextduedate

API-ключ выписывается в панели (My Servers → Configuration → Ключи API).
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.finance.adapters.base import (
    DEFAULT_TIMEOUT, AdapterError, AdapterField, HosterAdapter, Service, SyncResult,
    register_adapter,
)

logger = logging.getLogger(__name__)

_DEFAULT_BASE = "https://invapi.hostkey.ru"


@register_adapter
class HostkeyAdapter(HosterAdapter):
    slug = "hostkey"
    title = "Hostkey (Invapi)"
    description = "Клиентский API Hostkey поверх WHMCS. Ключ — в панели: Configuration → API keys."
    needs_base_url = False
    fields = [
        AdapterField("api_key", "API-ключ", type="password",
                     help="My Servers → Configuration → «Ключи API» → Add new (показывается один раз)."),
    ]

    def _base(self, base_url: Optional[str]) -> str:
        return (base_url or "").strip().rstrip("/") or _DEFAULT_BASE

    # Разные версии Invapi отдают токен на разных путях — пробуем оба.
    _AUTH_PATHS = ("auth.php", "auth/login")

    async def _token(self, client: httpx.AsyncClient, base: str, api_key: str) -> str:
        last = "нет ответа"
        for path in self._AUTH_PATHS:
            try:
                resp = await client.post(f"{base}/{path}", data={"api_key": api_key})
            except httpx.HTTPError as e:
                last = f"{path}: сеть/HTTP {e}"
                logger.info("Hostkey auth %s: %s", path, last)
                continue
            token = self._extract_token(resp)
            if token:
                return token
            last = f"{path}: HTTP {resp.status_code}, тело {resp.text[:200]!r}"
            logger.info("Hostkey auth %s не дал токен: %s", path, last)
        raise AdapterError(f"Не удалось получить токен по API-ключу ({last})")

    @staticmethod
    def _extract_token(resp: httpx.Response) -> Optional[str]:
        try:
            data = resp.json()
        except ValueError:
            return resp.text.strip().strip('"') or None
        if isinstance(data, dict):
            return (
                data.get("token") or data.get("HOSTKEY_TOKEN")
                or data.get("access_token") or data.get("session")
            )
        if isinstance(data, str):
            return data.strip() or None
        return None

    async def _call(self, client: httpx.AsyncClient, base: str, action: str, token: str,
                    extra: Optional[Dict[str, str]] = None) -> Any:
        payload = {"action": action, "token": token, **(extra or {})}
        try:
            resp = await client.post(f"{base}/whmcs.php", data=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            raise AdapterError(f"Сеть/HTTP ({action}): {e}")
        except ValueError:
            raise AdapterError(f"Некорректный ответ Invapi на {action}")

    async def fetch(self, base_url: Optional[str], credentials: Dict[str, str]) -> SyncResult:
        base = self._base(base_url)
        api_key = (credentials.get("api_key") or "").strip()
        if not api_key:
            raise AdapterError("Не заполнен API-ключ")

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
            token = await self._token(client, base, api_key)
            balance, currency = await self._fetch_balance(client, base, token)
            services = await self._fetch_services(client, base, token)
        return SyncResult(balance=balance, currency=currency, services=services)

    async def _fetch_balance(self, client, base, token):
        data = await self._call(client, base, "getcredits", token)
        currency = None
        total = 0.0
        found = False
        credits = data.get("credits") if isinstance(data, dict) else None
        rows = credits.get("credit") if isinstance(credits, dict) else credits
        if isinstance(rows, dict):
            rows = [rows]
        for c in (rows or []):
            if not isinstance(c, dict):
                continue
            try:
                total += float(c.get("amount") or 0)
                found = True
            except (TypeError, ValueError):
                continue
            currency = currency or c.get("currencycode") or c.get("currency")
        # прямое поле баланса, если есть
        if isinstance(data, dict) and data.get("balance") is not None:
            try:
                return round(float(data["balance"]), 2), (data.get("currency") or currency)
            except (TypeError, ValueError):
                pass
        return (round(total, 2) if found else None), currency

    async def _fetch_services(self, client, base, token) -> List[Service]:
        try:
            data = await self._call(client, base, "getclientsproducts", token)
        except AdapterError as e:
            logger.info("Hostkey getclientsproducts failed (%s), услуги пропущены", e)
            return []
        products = data.get("products") if isinstance(data, dict) else None
        rows = products.get("product") if isinstance(products, dict) else products
        if isinstance(rows, dict):
            rows = [rows]
        services: List[Service] = []
        for p in (rows or []):
            if not isinstance(p, dict):
                continue
            name = p.get("name") or p.get("productname") or p.get("domain")
            if not name:
                continue
            price = None
            try:
                price = round(float(p.get("recurringamount")), 2)
            except (TypeError, ValueError):
                pass
            services.append(Service(
                name=str(name),
                status=str(p.get("status") or "").lower() or None,
                price=price,
                currency=p.get("currencycode") or None,
                period=str(p.get("billingcycle") or "") or None,
                next_due_at=_iso_date(p.get("nextduedate")),
                external_id=str(p.get("id")) if p.get("id") is not None else None,
            ))
        return services


def _iso_date(v: Any) -> Optional[str]:
    if not v:
        return None
    s = str(v).strip().split(" ")[0]
    if s in ("0000-00-00", ""):
        return None
    parts = s.split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        return s
    return None
