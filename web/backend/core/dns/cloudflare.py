"""Cloudflare — DNS-провайдер (Bearer-токен Zone:Read + DNS:Edit)."""
import logging
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.dns.base import (
    DEFAULT_TIMEOUT, DnsField, DnsProvider, DnsProviderError, DnsRecord, DnsZone,
    register_provider,
)

logger = logging.getLogger(__name__)

CF_BASE = "https://api.cloudflare.com/client/v4"


@register_provider
class CloudflareProvider(DnsProvider):
    slug = "cloudflare"
    title = "Cloudflare"
    fields = [
        DnsField("token", "API-токен", type="password",
                 help="My Profile → API Tokens → права Zone:Read + DNS:Edit."),
    ]
    record_types = ["A", "AAAA", "CNAME", "TXT", "MX", "NS", "SRV", "CAA"]
    proxyable = ["A", "AAAA", "CNAME"]
    supports_ttl = True

    async def _req(self, token: Optional[str], method: str, path: str,
                   json_body: Optional[Dict[str, Any]] = None) -> Any:
        if not token:
            raise DnsProviderError("Cloudflare токен не настроен")
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=headers,
                                         follow_redirects=True) as client:
                resp = await client.request(method, f"{CF_BASE}{path}", json=json_body)
        except httpx.HTTPError as e:
            raise DnsProviderError(f"Сеть/HTTP: {e}")
        if resp.status_code in (401, 403):
            raise DnsProviderError("Токен отклонён или без прав (нужно Zone:Read + DNS:Edit)")
        try:
            data = resp.json()
        except ValueError:
            raise DnsProviderError(f"Некорректный ответ Cloudflare (HTTP {resp.status_code})")
        if isinstance(data, dict) and data.get("success") is False:
            errs = data.get("errors") or []
            msg = errs[0].get("message") if errs and isinstance(errs[0], dict) else f"HTTP {resp.status_code}"
            raise DnsProviderError(str(msg))
        if resp.status_code >= 400:
            raise DnsProviderError(f"Cloudflare HTTP {resp.status_code}")
        return data

    async def verify(self, creds: Dict[str, str]) -> bool:
        try:
            data = await self._req(creds.get("token"), "GET", "/user/tokens/verify")
        except DnsProviderError:
            return False
        r = data.get("result") if isinstance(data, dict) else None
        return bool(isinstance(r, dict) and r.get("status") == "active")

    async def list_zones(self, creds: Dict[str, str]) -> List[DnsZone]:
        data = await self._req(creds.get("token"), "GET", "/zones?per_page=50&order=name")
        return [DnsZone(id=str(z.get("id")), name=str(z.get("name")))
                for z in (data.get("result") or []) if isinstance(z, dict)]

    async def list_records(self, creds: Dict[str, str], zone_id: str) -> List[DnsRecord]:
        out: List[DnsRecord] = []
        page: Optional[int] = 1
        while page and len(out) < 1000:
            data = await self._req(
                creds.get("token"), "GET",
                f"/zones/{zone_id}/dns_records?per_page=100&page={page}&order=type")
            for r in (data.get("result") or []):
                if isinstance(r, dict):
                    out.append(_record(r))
            info = data.get("result_info") or {}
            total = info.get("total_pages")
            page = (page + 1) if (isinstance(total, int) and page < total) else None
        return out

    async def create_record(self, creds, zone_id, rec):
        data = await self._req(creds.get("token"), "POST",
                               f"/zones/{zone_id}/dns_records", _payload(rec))
        return _record(data.get("result") or {})

    async def update_record(self, creds, zone_id, record_id, rec):
        data = await self._req(creds.get("token"), "PUT",
                               f"/zones/{zone_id}/dns_records/{record_id}", _payload(rec))
        return _record(data.get("result") or {})

    async def delete_record(self, creds, zone_id, record_id):
        await self._req(creds.get("token"), "DELETE",
                        f"/zones/{zone_id}/dns_records/{record_id}")


def _record(r: Dict[str, Any]) -> DnsRecord:
    return DnsRecord(
        id=str(r.get("id") or ""), type=str(r.get("type") or ""),
        name=str(r.get("name") or ""), content=str(r.get("content") or ""),
        ttl=r.get("ttl"), proxied=r.get("proxied"), priority=r.get("priority"),
    )


def _payload(rec: Dict[str, Any]) -> Dict[str, Any]:
    rtype = str(rec.get("type") or "").upper()
    body: Dict[str, Any] = {
        "type": rtype,
        "name": str(rec.get("name") or "").strip(),
        "content": str(rec.get("content") or "").strip(),
        "ttl": int(rec.get("ttl") or 1),
    }
    if rtype in ("A", "AAAA", "CNAME"):
        body["proxied"] = bool(rec.get("proxied"))
    if rtype in ("MX", "SRV") and rec.get("priority") is not None:
        body["priority"] = int(rec["priority"])
    return body
