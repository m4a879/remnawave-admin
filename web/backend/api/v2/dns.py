"""DNS API — мульти-провайдерное управление записями зон.

Провайдеры: Cloudflare, Timeweb Cloud, reg.ru (реестр core.dns). Креды каждого
хранятся зашифрованными; правятся только через этот роутер. RBAC-ресурс `dns`.
"""
import logging
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from web.backend.api.deps import AdminUser, require_permission
from web.backend.core import dns as dnsmod
from web.backend.core.audit import write_audit_log

logger = logging.getLogger(__name__)
router = APIRouter()

_ALL_TYPES = ["A", "AAAA", "CNAME", "TXT", "MX", "NS", "SRV", "CAA"]


def _upstream(e: dnsmod.DnsProviderError) -> HTTPException:
    return HTTPException(status_code=502, detail=str(e))


def _provider(slug: str) -> dnsmod.DnsProvider:
    try:
        return dnsmod.get_provider(slug)
    except dnsmod.DnsProviderError as e:
        raise HTTPException(status_code=404, detail=str(e))


def _creds_or_400(slug: str) -> Dict[str, str]:
    creds = dnsmod.get_creds(slug)
    if creds is None:
        raise HTTPException(status_code=400, detail="Провайдер не подключён")
    return creds


# ── Схемы ────────────────────────────────────────────────────────


class CredsIn(BaseModel):
    creds: Dict[str, str]


class RecordIn(BaseModel):
    type: str
    name: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=4096)
    ttl: int = 1
    proxied: bool = False
    priority: Optional[int] = Field(default=None, ge=0, le=65535)

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        u = (v or "").upper()
        if u not in _ALL_TYPES:
            raise ValueError(f"type must be one of {', '.join(_ALL_TYPES)}")
        return u


# ── Провайдеры / креды ───────────────────────────────────────────


@router.get("/providers")
async def list_providers(admin: AdminUser = Depends(require_permission("dns", "view"))):
    return {"items": [p.to_meta(dnsmod.is_configured(p.slug)) for p in dnsmod.list_providers()]}


@router.put("/providers/{slug}/creds")
async def set_creds(slug: str, data: CredsIn,
                    admin: AdminUser = Depends(require_permission("dns", "edit"))):
    prov = _provider(slug)
    # Трим значений — токен, вставленный с пробелом/переносом строки,
    # иначе молча валит verify у любого провайдера
    data.creds = {k: v.strip() if isinstance(v, str) else v
                  for k, v in data.creds.items()}
    try:
        prov.validate_creds(data.creds)
    except dnsmod.DnsProviderError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        ok = await prov.verify(data.creds)
    except dnsmod.DnsProviderError as e:
        raise _upstream(e)
    if not ok:
        raise HTTPException(status_code=400, detail="Не удалось подключиться — проверь данные и права")
    await dnsmod.save_creds(slug, data.creds)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="dns.creds.set", resource="dns", resource_id=slug)
    return {"configured": True}


@router.delete("/providers/{slug}/creds")
async def clear_creds(slug: str, admin: AdminUser = Depends(require_permission("dns", "edit"))):
    _provider(slug)
    await dnsmod.clear_creds(slug)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="dns.creds.clear", resource="dns", resource_id=slug)
    return {"configured": False}


# ── Зоны / записи ────────────────────────────────────────────────


@router.get("/providers/{slug}/zones")
async def zones(slug: str, admin: AdminUser = Depends(require_permission("dns", "view"))):
    prov = _provider(slug)
    creds = _creds_or_400(slug)
    try:
        return {"items": [z.to_dict() for z in await prov.list_zones(creds)]}
    except dnsmod.DnsProviderError as e:
        raise _upstream(e)


@router.get("/providers/{slug}/zones/{zone_id}/records")
async def records(slug: str, zone_id: str,
                  admin: AdminUser = Depends(require_permission("dns", "view"))):
    prov = _provider(slug)
    creds = _creds_or_400(slug)
    try:
        return {"items": [r.to_dict() for r in await prov.list_records(creds, zone_id)]}
    except dnsmod.DnsProviderError as e:
        raise _upstream(e)


@router.post("/providers/{slug}/zones/{zone_id}/records")
async def create_record(slug: str, zone_id: str, data: RecordIn,
                        admin: AdminUser = Depends(require_permission("dns", "edit"))):
    prov = _provider(slug)
    creds = _creds_or_400(slug)
    try:
        rec = await prov.create_record(creds, zone_id, data.model_dump())
    except dnsmod.DnsProviderError as e:
        raise _upstream(e)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="dns.record.create", resource="dns",
                          resource_id=f"{slug}:{data.type} {data.name}")
    return rec.to_dict()


@router.put("/providers/{slug}/zones/{zone_id}/records/{record_id}")
async def update_record(slug: str, zone_id: str, record_id: str, data: RecordIn,
                        admin: AdminUser = Depends(require_permission("dns", "edit"))):
    prov = _provider(slug)
    creds = _creds_or_400(slug)
    try:
        rec = await prov.update_record(creds, zone_id, record_id, data.model_dump())
    except dnsmod.DnsProviderError as e:
        raise _upstream(e)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="dns.record.update", resource="dns",
                          resource_id=f"{slug}:{data.type} {data.name}")
    return rec.to_dict()


@router.delete("/providers/{slug}/zones/{zone_id}/records/{record_id}")
async def delete_record(slug: str, zone_id: str, record_id: str,
                        admin: AdminUser = Depends(require_permission("dns", "edit"))):
    prov = _provider(slug)
    creds = _creds_or_400(slug)
    try:
        await prov.delete_record(creds, zone_id, record_id)
    except dnsmod.DnsProviderError as e:
        raise _upstream(e)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="dns.record.delete", resource="dns", resource_id=f"{slug}:{record_id}")
    return {"deleted": True}
