"""Aeza — DNS-провайдер (my.aeza.net/api/v2, ключ в заголовке X-API-KEY).

Та же база и авторизация, что у финмодуль-адаптера Aeza. Эндпоинты (из панели):
- зоны:    GET    /api/v2/domains?limit=              -> data.items[] {id, name}
- записи:  GET    /api/v2/domains/{id}/records?limit= -> data.items[]
- create:  POST   /api/v2/domains/{id}/records
- update:  PUT    /api/v2/domains/{id}/records/{record_id}
- delete:  DELETE /api/v2/domains/{id}/records/{record_id}
Ответы обёрнуты в data. Проксирования нет; зона = числовой id домена.
Ключ: my.aeza.net → раздел API.
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.dns.base import (
    DEFAULT_TIMEOUT, DnsField, DnsProvider, DnsProviderError, DnsRecord, DnsZone,
    register_provider,
)

logger = logging.getLogger(__name__)

_BASE = "https://my.aeza.net/api/v2"


@register_provider
class AezaProvider(DnsProvider):
    slug = "aeza"
    title = "Aeza"
    fields = [
        DnsField("api_key", "API-ключ", type="password",
                 help="Панель my.aeza.net → раздел API → создать ключ."),
    ]
    # типы из /records/types Aeza (SRV требует вес/порт — вне общей модели, опущен)
    record_types = ["A", "AAAA", "CNAME", "TXT", "MX", "ALIAS", "DNAME"]
    proxyable = []
    supports_ttl = True

    async def _req(self, key: Optional[str], method: str, path: str,
                   json_body: Optional[Dict[str, Any]] = None) -> Any:
        if not key:
            raise DnsProviderError("Aeza ключ не настроен")
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers={"X-API-KEY": key},
                                         follow_redirects=True) as client:
                resp = await client.request(method, f"{_BASE}{path}", json=json_body)
        except httpx.HTTPError as e:
            raise DnsProviderError(f"Сеть/HTTP: {e}")
        if resp.status_code in (401, 403):
            raise DnsProviderError("Ключ Aeza отклонён")
        if resp.status_code == 204 or (resp.status_code < 300 and not resp.content):
            return {}
        try:
            data = resp.json()
        except ValueError:
            if resp.status_code >= 400:
                raise DnsProviderError(f"Aeza HTTP {resp.status_code}")
            return {}
        if resp.status_code >= 400:
            msg = None
            if isinstance(data, dict):
                err = data.get("error")
                msg = data.get("message") or (err.get("message") if isinstance(err, dict) else err)
            raise DnsProviderError(f"Aeza: {msg or f'HTTP {resp.status_code}'}")
        return data

    @staticmethod
    def _payload(data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
            return data["data"]
        return data

    @staticmethod
    def _items(data: Any) -> List[Dict[str, Any]]:
        if isinstance(data, dict):
            seq = data.get("items") or data.get("records") or data.get("domains") or []
        else:
            seq = data if isinstance(data, list) else []
        return [x for x in seq if isinstance(x, dict)]

    async def verify(self, creds: Dict[str, str]) -> bool:
        try:
            await self._req(creds.get("api_key"), "GET", "/domains?limit=1")
        except DnsProviderError:
            return False
        return True

    async def list_zones(self, creds: Dict[str, str]) -> List[DnsZone]:
        data = self._payload(await self._req(creds.get("api_key"), "GET", "/domains?limit=200"))
        out: List[DnsZone] = []
        for d in self._items(data):
            zid = d.get("id")
            name = d.get("name") or d.get("fqdn") or d.get("domain")
            if zid is not None and name:
                out.append(DnsZone(id=str(zid), name=str(name)))
        return out

    async def list_records(self, creds: Dict[str, str], zone_id: str) -> List[DnsRecord]:
        data = self._payload(await self._req(
            creds.get("api_key"), "GET", f"/domains/{zone_id}/records?limit=200"))
        return [_record(r) for r in self._items(data)]

    async def create_record(self, creds, zone_id, rec):
        data = self._payload(await self._req(
            creds.get("api_key"), "POST", f"/domains/{zone_id}/records", _payload_body(rec)))
        return _record(data if isinstance(data, dict) else {})

    async def update_record(self, creds, zone_id, record_id, rec):
        data = self._payload(await self._req(
            creds.get("api_key"), "PUT", f"/domains/{zone_id}/records/{record_id}", _payload_body(rec)))
        return _record(data if isinstance(data, dict) else {})

    async def delete_record(self, creds, zone_id, record_id):
        await self._req(creds.get("api_key"), "DELETE", f"/domains/{zone_id}/records/{record_id}")


def _record(r: Dict[str, Any]) -> DnsRecord:
    content = r.get("value")
    if content is None:
        content = r.get("content") or r.get("data") or ""
    prio = r.get("priority")
    if prio is None:
        prio = r.get("mxPriority") or r.get("mx_priority")
    return DnsRecord(
        id=str(r.get("id") or ""), type=str(r.get("type") or "").upper(),
        name=str(r.get("name") or r.get("subdomain") or "@"),
        content=str(content), ttl=r.get("ttl"), proxied=None, priority=prio,
    )


def _payload_body(rec: Dict[str, Any]) -> Dict[str, Any]:
    # поле значения у Aeza — `content` (slug из /records/types); MX = priority+content
    rtype = str(rec.get("type") or "").upper()
    body: Dict[str, Any] = {
        "type": rtype,
        "name": str(rec.get("name") or "").strip(),
        "content": str(rec.get("content") or "").strip(),
    }
    ttl = rec.get("ttl")
    if ttl and int(ttl) > 1:
        body["ttl"] = int(ttl)
    if rtype in ("MX", "SRV") and rec.get("priority") is not None:
        body["priority"] = int(rec["priority"])
    return body
