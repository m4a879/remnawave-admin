"""Selectel — DNS-провайдер (DNS API v1, статический X-Token).

База: https://api.selectel.ru/domains/v1
- зоны:    GET    /                       -> [{id, name}]
- записи:  GET    /{domain_id}/records/   -> [{id, type, name, content, ttl, priority}]
- create:  POST   /{domain_id}/records/
- update:  PUT    /{domain_id}/records/{record_id}
- delete:  DELETE /{domain_id}/records/{record_id}
Зона = числовой id домена (name — для отображения). Проксирования нет.
Ключ: Аккаунт → Доступ → Ключи API (статический).
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.dns.base import (
    DEFAULT_TIMEOUT, DnsField, DnsProvider, DnsProviderError, DnsRecord, DnsZone,
    register_provider,
)

logger = logging.getLogger(__name__)

_BASE = "https://api.selectel.ru/domains/v1"


@register_provider
class SelectelProvider(DnsProvider):
    slug = "selectel"
    title = "Selectel"
    fields = [
        DnsField("token", "API-ключ (X-Token)", type="password",
                 help="Аккаунт → Доступ → Ключи API → статический ключ."),
    ]
    record_types = ["A", "AAAA", "CNAME", "MX", "TXT", "NS", "SRV"]
    proxyable = []
    supports_ttl = True

    async def _req(self, token: Optional[str], method: str, path: str,
                   json_body: Optional[Dict[str, Any]] = None) -> Any:
        if not token:
            raise DnsProviderError("Selectel токен не настроен")
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers={"X-Token": token},
                                         follow_redirects=True) as client:
                resp = await client.request(method, f"{_BASE}{path}", json=json_body)
        except httpx.HTTPError as e:
            raise DnsProviderError(f"Сеть/HTTP: {e}")
        if resp.status_code in (401, 403):
            raise DnsProviderError("Токен Selectel отклонён")
        if resp.status_code == 204 or (resp.status_code == 200 and not resp.content):
            return {}
        try:
            data = resp.json()
        except ValueError:
            if resp.status_code >= 400:
                raise DnsProviderError(f"Selectel HTTP {resp.status_code}")
            return {}
        if resp.status_code >= 400:
            msg = None
            if isinstance(data, dict):
                msg = data.get("error") or data.get("description") or data.get("message")
            raise DnsProviderError(f"Selectel: {msg or f'HTTP {resp.status_code}'}")
        return data

    async def verify(self, creds: Dict[str, str]) -> bool:
        try:
            await self._req(creds.get("token"), "GET", "/")
        except DnsProviderError:
            return False
        return True

    async def list_zones(self, creds: Dict[str, str]) -> List[DnsZone]:
        data = await self._req(creds.get("token"), "GET", "/")
        items = data if isinstance(data, list) else (
            (data.get("result") or data.get("domains") or []) if isinstance(data, dict) else [])
        out: List[DnsZone] = []
        for d in items:
            if isinstance(d, dict) and d.get("id") is not None and d.get("name"):
                out.append(DnsZone(id=str(d["id"]), name=str(d["name"])))
        return out

    async def list_records(self, creds: Dict[str, str], zone_id: str) -> List[DnsRecord]:
        data = await self._req(creds.get("token"), "GET", f"/{zone_id}/records/")
        items = data if isinstance(data, list) else (
            (data.get("result") or data.get("records") or []) if isinstance(data, dict) else [])
        return [_record(r) for r in items if isinstance(r, dict)]

    async def create_record(self, creds, zone_id, rec):
        data = await self._req(creds.get("token"), "POST", f"/{zone_id}/records/", _payload(rec))
        return _record(data if isinstance(data, dict) else {})

    async def update_record(self, creds, zone_id, record_id, rec):
        data = await self._req(creds.get("token"), "PUT",
                               f"/{zone_id}/records/{record_id}", _payload(rec))
        return _record(data if isinstance(data, dict) else {})

    async def delete_record(self, creds, zone_id, record_id):
        await self._req(creds.get("token"), "DELETE", f"/{zone_id}/records/{record_id}")


def _record(r: Dict[str, Any]) -> DnsRecord:
    return DnsRecord(
        id=str(r.get("id") or ""), type=str(r.get("type") or "").upper(),
        name=str(r.get("name") or ""), content=str(r.get("content") or ""),
        ttl=r.get("ttl"), proxied=None, priority=r.get("priority"),
    )


def _payload(rec: Dict[str, Any]) -> Dict[str, Any]:
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
