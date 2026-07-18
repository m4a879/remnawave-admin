"""ISPsystem BILLmanager 5/6 — клиентский API.

Покрывает инстансы BILLmanager (waicore, h2.nexus, 1cent.host и т.п.).
Запросы: {base}/billmgr?func=<f>&out=json&authinfo=user:pass
- баланс:  func=subaccount → balance, currency
- услуги:  func=item        → name, cost, expiredate, status, pricelist

Ответ out=json оборачивает значения как {"$": "..."}, списки — в doc.elem.
Ошибка — наличие doc.error (тип в error.$type, текст в error.msg.$).
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.finance.adapters.base import (
    DEFAULT_TIMEOUT, AdapterError, AdapterField, HosterAdapter, Service, SyncResult,
    register_adapter,
)

logger = logging.getLogger(__name__)

# Коды статусов услуг BILLmanager (item.status)
_STATUS = {
    "1": "ordered", "2": "active", "3": "active", "4": "stopped",
    "5": "deleted", "6": "processing",
}

# Функции клиентского раздела BILLmanager со списками услуг. Разные инстансы/
# версии подключают разные модули, поэтому единый список услуг есть не везде
# (на некоторых func=item/service отвечает «управляющий модуль не загружен»).
# Сначала пробуем единый список, при недоступности — фолбэк на списки по типам.
_UNIFIED_SERVICE_FUNCS = ("service", "item")
_TYPED_SERVICE_FUNCS = ("vds", "instances", "vps", "dedic", "vhost", "domain", "soft", "certificate")


def _unwrap(v: Any) -> Any:
    """{"$": x} -> x; остальное как есть."""
    if isinstance(v, dict) and "$" in v and len(v) == 1:
        return v["$"]
    return v


def _field(record: Dict[str, Any], *keys: str) -> Optional[str]:
    for k in keys:
        if k in record:
            val = _unwrap(record[k])
            if val not in (None, ""):
                return str(val)
    return None


def _num(v: Optional[str]) -> Optional[float]:
    if v is None:
        return None
    try:
        return round(float(str(v).replace(",", ".").split()[0]), 2)
    except (ValueError, IndexError):
        return None


def _rows(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """doc.elem может быть списком, одиночным объектом или отсутствовать."""
    elem = doc.get("elem")
    if isinstance(elem, list):
        return [e for e in elem if isinstance(e, dict)]
    if isinstance(elem, dict):
        return [elem]
    return []


def _normalize_date(v: Optional[str]) -> Optional[str]:
    """BILLmanager отдаёт даты как YYYY-MM-DD; берём только дату."""
    if not v:
        return None
    v = str(v).strip().split(" ")[0]
    parts = v.split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        return v
    return None


@register_adapter
class BillmanagerAdapter(HosterAdapter):
    slug = "billmanager"
    title = "ISPsystem BILLmanager"
    description = "BILLmanager 5/6: Waicore, h2.nexus, 1cent.host и другие инстансы"
    needs_base_url = True
    fields = [
        AdapterField("username", "Логин (email)", type="text",
                     placeholder="client@mail.ru"),
        AdapterField("password", "Пароль", type="password",
                     help="Если включён 2FA или ограничение authinfo по IP — авторизация может не пройти."),
    ]

    def _endpoint(self, base_url: Optional[str]) -> str:
        base = (base_url or "").strip().rstrip("/")
        if not base:
            raise AdapterError("Не указан адрес биллинга")
        # base_url может быть https://host, https://host/billmgr или .../billmgr?func=logon
        base = base.split("?")[0].rstrip("/")
        if not base.endswith("/billmgr"):
            base = base + "/billmgr"
        return base

    async def _call(self, client: httpx.AsyncClient, endpoint: str, func: str,
                    credentials: Dict[str, str]) -> Dict[str, Any]:
        params = {
            "func": func, "out": "json",
            "authinfo": f"{credentials.get('username', '')}:{credentials.get('password', '')}",
        }
        try:
            resp = await client.get(endpoint, params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            raise AdapterError(f"Сеть/HTTP: {e}")
        except ValueError:
            raise AdapterError("Биллинг вернул не JSON (проверьте адрес)")

        doc = data.get("doc", data) if isinstance(data, dict) else {}
        err = doc.get("error") if isinstance(doc, dict) else None
        if err:
            etype = _unwrap(err.get("$type")) or _unwrap(err.get("type"))
            detail = err.get("detail") if isinstance(err.get("detail"), dict) else {}
            msg = _field(err, "msg") or _field(detail, "$")
            if etype in ("auth", "authtype") or (msg and "парол" in str(msg).lower()):
                raise AdapterError(f"Ошибка авторизации: {msg or etype}")
            if etype == "access":
                raise AdapterError(f"Недостаточно прав: {msg or 'функция недоступна'}")
            raise AdapterError(str(msg or etype or "Ошибка BILLmanager"))
        return doc if isinstance(doc, dict) else {}

    async def fetch(self, base_url: Optional[str], credentials: Dict[str, str]) -> SyncResult:
        endpoint = self._endpoint(base_url)
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
            balance, currency = await self._fetch_balance(client, endpoint, credentials)
            services = await self._fetch_services(client, endpoint, credentials)
        return SyncResult(balance=balance, currency=currency, services=services)

    async def _fetch_balance(self, client, endpoint, credentials):
        doc = await self._call(client, endpoint, "subaccount", credentials)
        rows = _rows(doc)
        # баланс может лежать в записи subaccount или прямо в doc
        candidates = rows or ([doc] if doc else [])
        for rec in candidates:
            bal = _num(_field(rec, "balance"))
            if bal is not None:
                cur = _field(rec, "currency", "currency_iso", "iso") or _field(rec, "money_currency")
                return bal, (cur.upper() if cur else None)
        # запасной раздел
        try:
            doc2 = await self._call(client, endpoint, "account", credentials)
            for rec in (_rows(doc2) or [doc2]):
                bal = _num(_field(rec, "balance"))
                if bal is not None:
                    cur = _field(rec, "currency", "iso")
                    return bal, (cur.upper() if cur else None)
        except AdapterError:
            pass
        return None, None

    async def _fetch_services(self, client, endpoint, credentials) -> List[Service]:
        # 1) единый список услуг клиента, если модуль доступен
        for func in _UNIFIED_SERVICE_FUNCS:
            rows = await self._try_list(client, endpoint, func, credentials)
            if rows:
                return self._services_from_rows(rows)
        # 2) фолбэк: списки по типам, склеиваем и дедупим по id
        services: List[Service] = []
        seen: set = set()
        for func in _TYPED_SERVICE_FUNCS:
            rows = await self._try_list(client, endpoint, func, credentials)
            for svc in self._services_from_rows(rows):
                key = svc.external_id or f"{func}:{svc.name}"
                if key in seen:
                    continue
                seen.add(key)
                services.append(svc)
        if not services:
            # 3) автообнаружение: у части инстансов услуги в подмодулях
            # (Waicore: vds пуст, реальные VPS в vds.vps) — берём funcs из
            # секции «Товары/услуги» клиентского меню и пробуем их
            tried = set(_UNIFIED_SERVICE_FUNCS) | set(_TYPED_SERVICE_FUNCS)
            for func in await self._menu_service_funcs(client, endpoint, credentials):
                if func in tried:
                    continue
                tried.add(func)
                rows = await self._try_list(client, endpoint, func, credentials)
                for svc in self._services_from_rows(rows):
                    key = svc.external_id or f"{func}:{svc.name}"
                    if key in seen:
                        continue
                    seen.add(key)
                    services.append(svc)
        return services

    async def _menu_service_funcs(self, client, endpoint, credentials) -> List[str]:
        """func=menu -> имена функций из секции услуг (mainmenuservice).

        Меню — вложенные узлы с $name; секция услуг перечисляет модули,
        доступные клиенту (включая подтипы вида vds.vps).
        """
        try:
            doc = await self._call(client, endpoint, "menu", credentials)
        except AdapterError as e:
            logger.info("BILLmanager func=menu недоступна (%s)", e)
            return []

        def node_name(node: Dict[str, Any]) -> Optional[str]:
            nm = _unwrap(node.get("$name")) or _unwrap(node.get("name"))
            return str(nm) if nm else None

        def find_section(node: Any, name: str) -> Optional[Dict[str, Any]]:
            if isinstance(node, dict):
                if node_name(node) == name:
                    return node
                for v in node.values():
                    found = find_section(v, name)
                    if found is not None:
                        return found
            elif isinstance(node, list):
                for x in node:
                    found = find_section(x, name)
                    if found is not None:
                        return found
            return None

        def collect_names(node: Any, out: List[str]) -> None:
            if isinstance(node, dict):
                nm = node_name(node)
                if nm:
                    out.append(nm)
                for v in node.values():
                    collect_names(v, out)
            elif isinstance(node, list):
                for x in node:
                    collect_names(x, out)

        section = find_section(doc, "mainmenuservice")
        if section is None:
            logger.info("BILLmanager: секция mainmenuservice в меню не найдена")
            return []
        names: List[str] = []
        collect_names(section, names)
        funcs = [n for n in names if n != "mainmenuservice"][:20]
        logger.info("BILLmanager funcs секции услуг: %s", funcs)
        return funcs

    async def _try_list(self, client, endpoint, func, credentials) -> List[Dict[str, Any]]:
        """Вызвать func со списком услуг; вернуть строки, [] если функция недоступна.

        Отсутствие функции («управляющий модуль не загружен») — не ошибка синка,
        а сигнал, что этот тип услуг у данного инстанса не подключён.
        """
        try:
            doc = await self._call(client, endpoint, func, credentials)
        except AdapterError as e:
            logger.info("BILLmanager func=%s недоступна (%s)", func, e)
            return []
        rows = _rows(doc)
        if rows:
            logger.info("BILLmanager func=%s: услуг %d", func, len(rows))
        else:
            # функция отвечает, но список пуст — ключи и elem покажут,
            # в каком поле инстанс держит услуги (не doc.elem)
            logger.debug(
                "BILLmanager func=%s: пусто, keys=%s, elem=%r",
                func, [k for k in doc.keys() if not k.startswith("$")] or list(doc.keys())[:25],
                str(doc.get("elem"))[:200],
            )
        return rows

    @staticmethod
    def _services_from_rows(rows: List[Dict[str, Any]]) -> List[Service]:
        out: List[Service] = []
        for rec in rows:
            name = _field(rec, "name", "domain", "pricelist")
            if not name:
                continue
            status_raw = _field(rec, "status")
            cost = _field(rec, "cost", "item_cost")
            # краткие характеристики: тариф + датацентр/локация, если есть и не дублируют имя
            specs_parts: List[str] = []
            for extra in (_field(rec, "pricelist"), _field(rec, "datacenter", "dc", "location")):
                if extra and extra != name and extra not in specs_parts:
                    specs_parts.append(extra)
            out.append(Service(
                name=name,
                status=_STATUS.get(status_raw or "", status_raw),
                price=_num(cost) if cost is not None else None,
                currency=None,
                period=_field(rec, "period"),
                next_due_at=_normalize_date(_field(rec, "expiredate", "expire")),
                external_id=_field(rec, "id"),
                specs=" · ".join(specs_parts) or None,
            ))
        return out
