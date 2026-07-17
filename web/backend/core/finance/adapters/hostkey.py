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


def _dig(payload: Any, *keys: str) -> Any:
    """Спуститься по вложенным dict-ключам (пропуская отсутствующие)."""
    node = payload
    for k in keys:
        if isinstance(node, dict) and k in node:
            node = node[k]
    return node


def _as_list(node: Any) -> List[Dict[str, Any]]:
    if isinstance(node, dict):
        node = [node]
    return [x for x in node if isinstance(x, dict)] if isinstance(node, list) else []


def _credit_rows(payload: Any) -> List[Dict[str, Any]]:
    """getcredits: message.credits.credit[] (с запасом на более плоские формы)."""
    node = payload
    if isinstance(node, dict) and isinstance(node.get("message"), dict):
        node = node["message"]
    node = _dig(node, "credits", "credit") if isinstance(node, dict) else node
    return _as_list(node)


def _server_rows(payload: Any) -> List[Dict[str, Any]]:
    """eq.php list: серверы под message.{servers|list|server} либо плоско."""
    node = payload
    if isinstance(node, dict) and isinstance(node.get("message"), dict):
        node = node["message"]
    if isinstance(node, dict):
        for k in ("servers", "list", "server", "data", "items"):
            if isinstance(node.get(k), list):
                return _as_list(node[k])
        vals = [v for v in node.values() if isinstance(v, dict)]
        return vals if vals else []
    return _as_list(node)


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
                self._auth_payload = self._payload_of(resp)
                # лог без токена — вдруг есть валюта/полезные поля
                logger.info("Hostkey auth ok, ключи payload=%s", list(self._auth_payload.keys()))
                return token
            last = f"{mode} ({','.join(fields)}): HTTP {resp.status_code}, тело {resp.text[:200]!r}"
            logger.info("Hostkey auth не дал токен: %s", last)
        raise AdapterError(f"Не удалось получить токен по API-ключу ({last})")

    @staticmethod
    def _payload_of(resp: httpx.Response) -> Dict[str, Any]:
        try:
            inner, _ = _unwrap_envelope(resp.json())
        except ValueError:
            return {}
        return inner if isinstance(inner, dict) else {}

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
                    extra: Optional[Dict[str, str]] = None, endpoint: str = "whmcs.php") -> Any:
        """Вызов invapi endpoint с action+token; разворачивает конверт result/error."""
        payload = {"action": action, "token": token, **(extra or {})}
        try:
            resp = await client.post(f"{base}/{endpoint}", data=payload)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            raise AdapterError(f"Сеть/HTTP ({action}): {e}")
        except ValueError:
            raise AdapterError(f"Некорректный ответ Invapi на {action}")
        logger.info("Hostkey %s/%s raw: %s", endpoint, action, str(data)[:400])
        inner, err = _unwrap_envelope(data)
        if err:
            raise AdapterError(f"{action}: {err}")
        return inner

    async def fetch(self, base_url: Optional[str], credentials: Dict[str, str]) -> SyncResult:
        base = self._base(base_url)
        api_key = (credentials.get("api_key") or "").strip()
        if not api_key:
            raise AdapterError("Не заполнен API-ключ")
        self._auth_payload: Dict[str, Any] = {}

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
            token = await self._token(client, base, api_key)
            balance, currency = await self._fetch_balance(client, base, token)
            services = await self._fetch_services(client, base, token)
        return SyncResult(balance=balance, currency=currency or self._currency(base), services=services)

    def _currency(self, base: str) -> Optional[str]:
        """Валюта из auth-ответа, иначе инференс по домену invapi (.ru -> RUB)."""
        auth = getattr(self, "_auth_payload", {}) or {}
        for k in ("currency", "currency_code", "currencycode", "default_currency"):
            v = auth.get(k)
            if v:
                return str(v).upper()
        b = (base or "").lower()
        if b.endswith(".ru") or ".ru/" in b or ".ru:" in b:
            return "RUB"
        return "USD"

    async def _fetch_balance(self, client, base, token):
        # getcredits: леджер кредитов message.credits.credit[]; сумма amount
        # (с минусами) = текущий доступный кредит. Валюты в записях обычно нет.
        data = await self._call(client, base, "getcredits", token)
        total = 0.0
        found = False
        currency = None
        for c in _credit_rows(data):
            try:
                total += float(c.get("amount") or 0)
                found = True
            except (TypeError, ValueError):
                continue
            currency = currency or c.get("currencycode") or c.get("currency")
        return (round(total, 2) if found else None), currency

    async def _fetch_services(self, client, base, token) -> List[Service]:
        # У Hostkey нет getclientsproducts (invalid command) — услуги/серверы
        # отдаёт eq.php action=list.
        try:
            data = await self._call(client, base, "list", token, endpoint="eq.php")
        except AdapterError as e:
            logger.info("Hostkey eq.php list недоступен (%s), услуги пропущены", e)
            return []
        services: List[Service] = []
        for s in _server_rows(data):
            name = (s.get("name") or s.get("hostname") or s.get("server_name")
                    or s.get("domain") or s.get("ip") or s.get("title"))
            if not name:
                continue
            services.append(Service(
                name=str(name),
                status=str(s.get("status") or "").lower() or None,
                price=_first_num(s, "cost", "price", "monthly", "recurringamount", "amount"),
                currency=None,
                period=str(s.get("billingcycle") or s.get("period") or "") or None,
                next_due_at=_iso_date(
                    s.get("expiredate") or s.get("nextduedate") or s.get("paiddate")
                    or s.get("payment_date") or s.get("paid_till") or s.get("expires")
                ),
                external_id=str(s.get("id")) if s.get("id") is not None else None,
            ))
        return services


def _first_num(d: Dict[str, Any], *keys: str) -> Optional[float]:
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            try:
                return round(float(v), 2)
            except (TypeError, ValueError):
                continue
    return None


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
