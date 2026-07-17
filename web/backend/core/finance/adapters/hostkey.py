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


def _unwrap_envelope(data: Any):
    """Hostkey заворачивает ответ в `result`.

    Варианты result:
    - dict/list  -> это payload (напр. auth: {"result":{"token":...}});
    - число < 0 либо наличие `error` без payload -> ошибка;
    - строка-статус ("OK") -> успех, payload в ОСТАЛЬНЫХ ключах верхнего уровня
      (напр. {"result":"OK","credits":{...}}).
    Возвращает (payload, error): payload=None при ошибке.
    """
    if isinstance(data, dict) and "result" in data:
        res = data["result"]
        if isinstance(res, bool):  # на всякий, bool — подкласс int
            res = None
        if isinstance(res, (int, float)) and res < 0:
            return None, str(data.get("error") or f"result={res}")
        if isinstance(res, (dict, list)):
            return res, None
        if data.get("error"):
            return None, str(data["error"])
        # result="OK"/статус -> данные в остальных ключах
        return {k: v for k, v in data.items() if k != "result"}, None
    return data, None


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
        b = (base_url or "").strip().rstrip("/")
        # Invapi живёт на invapi.hostkey.* — НЕ на сайте провайдера hostkey.ru.
        # Если в base_url случайно попал адрес сайта (префилл провайдера),
        # берём дефолтный invapi-эндпоинт.
        if not b or "invapi" not in b.lower():
            return _DEFAULT_BASE
        return b

    async def _token(self, client: httpx.AsyncClient, base: str, api_key: str) -> str:
        """Обменять API-ключ на сессионный токен.

        invapi/auth.php ждёт action=login + ключ в параметре `key` (как в
        ссылке на панель ?key=...) и возвращает access_token. Ошибка приходит
        конвертом {"result":-N,"error":...}. Формат перебираем на случай
        вариаций инстанса (порядок параметров/имя ключа/метод).
        """
        attempts = (
            ("post_form", {"action": "login", "key": api_key}),
            ("post_form", {"action": "login", "api_key": api_key}),
            ("post_json", {"action": "login", "key": api_key}),
            ("get", {"action": "login", "key": api_key}),
            ("post_form", {"key": api_key}),
            ("post_form", {"api_key": api_key}),
        )
        url = f"{base}/auth.php"
        last = "нет ответа"
        for mode, fields in attempts:
            try:
                if mode == "post_json":
                    resp = await client.post(url, json=fields)
                elif mode == "get":
                    resp = await client.get(url, params=fields)
                else:
                    resp = await client.post(url, data=fields)
            except httpx.HTTPError as e:
                last = f"{mode}: сеть/HTTP {e}"
                logger.info("Hostkey auth %s", last)
                continue
            token = self._extract_token(resp)
            if token:
                return token
            last = f"{mode} ({','.join(fields)}): HTTP {resp.status_code}, тело {resp.text[:200]!r}"
            logger.info("Hostkey auth не дал токен: %s", last)
        raise AdapterError(f"Не удалось получить токен по API-ключу ({last})")

    @staticmethod
    def _extract_token(resp: httpx.Response) -> Optional[str]:
        try:
            data = resp.json()
        except ValueError:
            # не JSON: принимаем только короткую опаковую строку-токен,
            # а не HTML-страницу сайта (иначе сбой авторизации маскируется)
            t = resp.text.strip().strip('"')
            if t and "<" not in t and len(t) <= 256:
                return t
            return None

        # токен внутри конверта: {"result":{"token":...}}
        payload, err = _unwrap_envelope(data)
        if err or payload is None:
            return None

        def _pick(d: Dict[str, Any]) -> Optional[str]:
            return (
                d.get("token") or d.get("access_token")
                or d.get("session") or d.get("HOSTKEY_TOKEN")
            )

        if isinstance(payload, dict):
            tok = _pick(payload)
            if not tok and isinstance(payload.get("data"), dict):
                tok = _pick(payload["data"])
            return tok
        if isinstance(payload, str):
            return payload.strip() or None
        return None

    async def _call(self, client: httpx.AsyncClient, base: str, action: str, token: str,
                    extra: Optional[Dict[str, str]] = None) -> Any:
        """Вызов whmcs.php с action+token; разворачивает конверт result/error."""
        payload = {"action": action, "token": token, **(extra or {})}
        try:
            resp = await client.post(f"{base}/whmcs.php", data=payload)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            raise AdapterError(f"Сеть/HTTP ({action}): {e}")
        except ValueError:
            raise AdapterError(f"Некорректный ответ Invapi на {action}")
        logger.info("Hostkey %s raw: %s", action, str(data)[:400])
        inner, err = _unwrap_envelope(data)
        if err:
            raise AdapterError(f"{action}: {err}")
        return inner

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
        # payload уже развёрнут из result: список кредитов, {"credits":[...]},
        # {"credits":{"credit":[...]}} или прямое {"amount":..,"currencycode":..}
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            credits = data.get("credits", data.get("credit"))
            rows = credits.get("credit") if isinstance(credits, dict) else credits
            if rows is None and ("amount" in data or "balance" in data):
                rows = [data]
        else:
            rows = None
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
            logger.info("Hostkey getclientsproducts недоступен (%s), услуги пропущены", e)
            return []
        if isinstance(data, list):
            data = {"products": {"product": data}}
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
