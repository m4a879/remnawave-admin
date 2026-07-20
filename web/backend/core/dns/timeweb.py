"""Timeweb Cloud — DNS-провайдер (Bearer-токен).

- зоны:    GET    /api/v1/domains -> domains[].fqdn
- записи:  GET    /api/v1/domains/{fqdn}/dns-records -> dns_records[]
           запись: {id, type, data:{value, subdomain, priority}, ttl}
- create:  POST   /api/v1/domains/{fqdn}/dns-records (тело плоское)
- update:  PATCH  /api/v1/domains/{fqdn}/dns-records/{id}
- delete:  DELETE /api/v1/domains/{fqdn}/dns-records/{id}
Проксирования нет; зона = FQDN домена. Токен: панель → «API и терминал».
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.dns.base import (
    DEFAULT_TIMEOUT, DnsField, DnsProvider, DnsProviderError, DnsRecord, DnsZone,
    register_provider,
)

logger = logging.getLogger(__name__)

_BASE = "https://api.timeweb.cloud"


@register_provider
class TimewebProvider(DnsProvider):
    slug = "timeweb"
    title = "Timeweb Cloud"
    fields = [
        DnsField("token", "API-токен", type="password",
                 help="Панель Timeweb Cloud → «API и терминал» → создать токен."),
    ]
    record_types = ["A", "AAAA", "CNAME", "MX", "TXT"]
    proxyable = []
    supports_ttl = True

    async def _req(self, token: Optional[str], method: str, path: str,
                   json_body: Optional[Dict[str, Any]] = None) -> Any:
        if not token:
            raise DnsProviderError("Timeweb токен не настроен")
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=headers,
                                         follow_redirects=True) as client:
                resp = await client.request(method, f"{_BASE}{path}", json=json_body)
        except httpx.HTTPError as e:
            raise DnsProviderError(f"Сеть/HTTP: {e}")
        if resp.status_code in (401, 403):
            raise DnsProviderError("Токен Timeweb отклонён")
        if resp.status_code == 204:
            return {}
        try:
            data = resp.json()
        except ValueError:
            if resp.status_code >= 400:
                raise DnsProviderError(f"Timeweb HTTP {resp.status_code}")
            return {}
        if resp.status_code >= 400:
            msg = None
            if isinstance(data, dict):
                msg = data.get("message") or (data.get("error") or {}).get("message") \
                    if isinstance(data.get("error"), dict) else data.get("message")
            raise DnsProviderError(f"Timeweb: {msg or f'HTTP {resp.status_code}'}")
        return data

    async def verify(self, creds: Dict[str, str]) -> bool:
        try:
            await self._req(creds.get("token"), "GET", "/api/v1/domains?limit=1")
        except DnsProviderError:
            return False
        return True

    async def list_zones(self, creds: Dict[str, str]) -> List[DnsZone]:
        data = await self._req(creds.get("token"), "GET", "/api/v1/domains?limit=100")
        out: List[DnsZone] = []
        for d in (data.get("domains") or []):
            if isinstance(d, dict) and d.get("fqdn"):
                out.append(DnsZone(id=str(d["fqdn"]), name=str(d["fqdn"])))
        return out

    async def list_records(self, creds: Dict[str, str], zone_id: str) -> List[DnsRecord]:
        data = await self._req(creds.get("token"), "GET",
                               f"/api/v1/domains/{zone_id}/dns-records?limit=1000")
        return [_record(r) for r in (data.get("dns_records") or []) if isinstance(r, dict)]

    async def create_record(self, creds, zone_id, rec):
        data = await self._req(creds.get("token"), "POST",
                               f"/api/v1/domains/{zone_id}/dns-records", _payload(rec))
        return _record(data.get("dns_record") or {})

    async def update_record(self, creds, zone_id, record_id, rec):
        data = await self._req(creds.get("token"), "PATCH",
                               f"/api/v1/domains/{zone_id}/dns-records/{record_id}", _payload(rec))
        return _record(data.get("dns_record") or {})

    async def delete_record(self, creds, zone_id, record_id):
        await self._req(creds.get("token"), "DELETE",
                        f"/api/v1/domains/{zone_id}/dns-records/{record_id}")


def _record(r: Dict[str, Any]) -> DnsRecord:
    d = r.get("data") if isinstance(r.get("data"), dict) else {}
    sub = d.get("subdomain")
    return DnsRecord(
        id=str(r.get("id") or ""), type=str(r.get("type") or ""),
        name=str(sub) if sub else "@", content=str(d.get("value") or ""),
        ttl=r.get("ttl"), proxied=None, priority=d.get("priority"),
    )


def _payload(rec: Dict[str, Any]) -> Dict[str, Any]:
    name = str(rec.get("name") or "").strip()
    sub = "" if name in ("@", "") else name
    body: Dict[str, Any] = {
        "type": str(rec.get("type") or "").upper(),
        "value": str(rec.get("content") or "").strip(),
        "subdomain": sub,
    }
    ttl = rec.get("ttl")
    if ttl and int(ttl) > 1:
        body["ttl"] = int(ttl)
    if str(rec.get("type")).upper() == "MX" and rec.get("priority") is not None:
        body["priority"] = int(rec["priority"])
    return body
