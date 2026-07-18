"""Hostkey Invapi — клиентский API (обёртка над WHMCS).

База: https://invapi.hostkey.ru (RU) или .com. Поток:
1. api_key -> сессионный токен (POST auth.php, action=login&key=...)
2. баланс: POST whmcs.php action=getcredits, token=... -> сумма кредитов
3. услуги: eq.php action=list -> id серверов, затем по каждому
   eq.php action=show (железо/локация) + whmcs.php action=get_billing_data (цена/продление)

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
        # eq.php action=list отдаёт список серверов. На большинстве инстансов это
        # ГОЛЫЕ id (servers:[55054]) — тогда детали тянем поштучно:
        #   eq.php  action=show           id=<id> -> имя, hwconfig, локация
        #   whmcs.php action=get_billing_data id=<id> -> цена, дата продления
        # Если же list вернул полные записи — используем их без доп. запросов.
        try:
            data = await self._call(client, base, "list", token, endpoint="eq.php")
        except AdapterError as e:
            logger.info("Hostkey eq.php list недоступен (%s), услуги пропущены", e)
            return []
        services: List[Service] = []
        for sid, row in _server_entries(data)[:50]:  # cap: не долбим API при большом флоте
            svc = _service_from_row(row) if row else None
            if sid is not None and (svc is None or not svc.name or svc.price is None):
                svc = await self._enrich_server(client, base, token, sid, svc)
            if svc and svc.name:
                services.append(svc)
        return services

    async def _enrich_server(self, client, base, token, sid: str,
                             base_svc: Optional[Service]) -> Service:
        """Добрать имя/железо (eq.php show) и цену/продление (whmcs get_billing_data)."""
        name = base_svc.name if base_svc else None
        status = base_svc.status if base_svc else None
        price = base_svc.price if base_svc else None
        period = base_svc.period if base_svc else None
        next_due = base_svc.next_due_at if base_svc else None
        currency = base_svc.currency if base_svc else None
        specs = base_svc.specs if base_svc else None

        try:
            det = await self._call(client, base, "show", token,
                                   extra={"id": str(sid)}, endpoint="eq.php")
            rec = _detail_rec(det)
            if rec:
                name = name or _pick_str(rec, "name", "hostname", "server_name", "title")
                status = status or (str(rec.get("status") or "").lower() or None)
                specs = specs or _hwconfig_specs(rec)
        except AdapterError as e:
            logger.info("Hostkey eq.php show id=%s: %s", sid, e)

        try:
            bill = await self._call(client, base, "get_billing_data", token,
                                    extra={"id": str(sid)}, endpoint="whmcs.php")
            brec = _detail_rec(bill)
            if brec:
                if price is None:
                    price = _first_num(brec, "recurringamount", "amount", "cost",
                                       "price", "total", "firstpaymentamount")
                period = period or (str(brec.get("billingcycle") or brec.get("period") or "") or None)
                next_due = next_due or _iso_date(
                    brec.get("nextduedate") or brec.get("duedate") or brec.get("expiredate"))
                currency = currency or brec.get("currencycode") or brec.get("currency")
        except AdapterError as e:
            logger.info("Hostkey whmcs get_billing_data id=%s: %s", sid, e)

        return Service(
            name=str(name or f"#{sid}"), status=status, price=price,
            currency=(str(currency).upper() if currency else None),
            period=period, next_due_at=next_due, external_id=str(sid), specs=specs,
        )


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


def _pick_str(d: Dict[str, Any], *keys: str) -> Optional[str]:
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return str(v)
    return None


def _server_entries(payload: Any) -> List[tuple]:
    """Из eq.php list вернуть [(id, row|None)].

    row — dict, если инстанс отдал запись целиком; None — если только id
    (servers:[55054]). Список серверов бывает под message.* или на верхнем уровне.
    """
    node = payload
    if isinstance(node, dict) and isinstance(node.get("message"), dict):
        node = node["message"]
    seq: Any = None
    if isinstance(node, dict):
        for k in ("servers", "list", "server", "data", "items", "ids"):
            if isinstance(node.get(k), list):
                seq = node[k]
                break
        if seq is None:
            seq = [v for v in node.values() if isinstance(v, (dict, int, str))]
    elif isinstance(node, list):
        seq = node
    entries: List[tuple] = []
    for item in (seq or []):
        if isinstance(item, dict):
            sid = item.get("id") or item.get("server_id") or item.get("eq_id")
            entries.append((str(sid) if sid is not None else None, item))
        elif item not in (None, "", True, False):
            entries.append((str(item), None))
    return entries


def _service_from_row(r: Dict[str, Any]) -> Service:
    """Собрать услугу из записи eq.php list (если инстанс отдаёт её целиком)."""
    name = _pick_str(r, "name", "hostname", "server_name", "domain", "ip", "title")
    sid = r.get("id") or r.get("server_id") or r.get("eq_id")
    return Service(
        name=str(name or ""),
        status=str(r.get("status") or "").lower() or None,
        price=_first_num(r, "cost", "price", "monthly", "recurringamount", "amount"),
        currency=None,
        period=str(r.get("billingcycle") or r.get("period") or "") or None,
        next_due_at=_iso_date(
            r.get("expiredate") or r.get("nextduedate") or r.get("paiddate")
            or r.get("payment_date") or r.get("paid_till") or r.get("expires")
        ),
        external_id=str(sid) if sid is not None else None,
        specs=_hwconfig_specs(r),
    )


def _detail_rec(payload: Any) -> Optional[Dict[str, Any]]:
    """Достать запись сервера из ответа show/get_billing_data (снять message-обёртку)."""
    node = payload
    if isinstance(node, dict) and isinstance(node.get("message"), dict):
        node = node["message"]
    if isinstance(node, dict):
        for k in ("server", "eq", "data", "info", "product", "service", "billing"):
            if isinstance(node.get(k), dict):
                return node[k]
        return node
    if isinstance(node, list):
        for x in node:
            if isinstance(x, dict):
                return x
    return None


def _hwconfig_specs(rec: Dict[str, Any]) -> Optional[str]:
    """Краткие характеристики: CPU/RAM/диск из hwconfig + локация."""
    hw = rec.get("hwconfig") or rec.get("config") or rec.get("configuration")
    parts: List[str] = []
    if isinstance(hw, dict):
        for key in ("cpu", "processor", "ram", "memory", "disk", "hdd", "ssd", "storage"):
            v = hw.get(key)
            if v:
                parts.append(str(v))
    elif isinstance(hw, str) and hw.strip():
        parts.append(hw.strip())
    loc = _pick_str(rec, "location", "city", "datacenter", "country", "region")
    if loc and loc not in parts:
        parts.append(loc)
    specs = " · ".join(p for p in parts if p)
    return specs[:200] or None
