"""DNS API — управление записями зон Cloudflare из админки.

Токен (Zone:Read + DNS:Edit) хранится зашифрованным; правится только через
этот роутер. RBAC-ресурс `dns` (view/edit).
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from web.backend.api.deps import AdminUser, require_permission
from web.backend.core import cloudflare_dns as cf
from web.backend.core.audit import write_audit_log

logger = logging.getLogger(__name__)
router = APIRouter()


def _cf_guard(e: cf.CloudflareDnsError) -> HTTPException:
    return HTTPException(status_code=502, detail=str(e))


# ── Схемы ────────────────────────────────────────────────────────


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class RecordIn(BaseModel):
    type: str
    name: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=2048)
    ttl: int = 1  # 1 = automatic
    proxied: bool = False
    priority: Optional[int] = Field(default=None, ge=0, le=65535)
    comment: Optional[str] = Field(default=None, max_length=100)

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        u = (v or "").upper()
        if u not in cf.RECORD_TYPES:
            raise ValueError(f"type must be one of {', '.join(cf.RECORD_TYPES)}")
        return u

    @field_validator("ttl")
    @classmethod
    def _ttl(cls, v: int) -> int:
        # 1 = automatic; иначе Cloudflare требует 60..86400
        if v != 1 and not (60 <= v <= 86400):
            raise ValueError("ttl must be 1 (auto) or between 60 and 86400")
        return v


# ── Токен ────────────────────────────────────────────────────────


@router.get("/status")
async def dns_status(admin: AdminUser = Depends(require_permission("dns", "view"))):
    return {"configured": cf.is_configured(), "record_types": cf.RECORD_TYPES,
            "proxyable": sorted(cf.PROXYABLE)}


@router.put("/token")
async def set_token(data: TokenIn, admin: AdminUser = Depends(require_permission("dns", "edit"))):
    # проверяем токен до сохранения — не храним заведомо нерабочий
    if not await cf.verify_token(data.token.strip()):
        raise HTTPException(status_code=400, detail="Токен недействителен или без нужных прав")
    await cf.save_token(data.token)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="dns.token.set", resource="dns", resource_id="token")
    return {"configured": True, "verified": True}


@router.delete("/token")
async def delete_token(admin: AdminUser = Depends(require_permission("dns", "edit"))):
    await cf.clear_token()
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="dns.token.clear", resource="dns", resource_id="token")
    return {"configured": False}


# ── Зоны и записи ────────────────────────────────────────────────


@router.get("/zones")
async def get_zones(admin: AdminUser = Depends(require_permission("dns", "view"))):
    try:
        return {"items": await cf.list_zones()}
    except cf.CloudflareDnsError as e:
        raise _cf_guard(e)


@router.get("/zones/{zone_id}/records")
async def get_records(zone_id: str, admin: AdminUser = Depends(require_permission("dns", "view"))):
    try:
        return {"items": await cf.list_records(zone_id)}
    except cf.CloudflareDnsError as e:
        raise _cf_guard(e)


@router.post("/zones/{zone_id}/records")
async def post_record(zone_id: str, data: RecordIn,
                      admin: AdminUser = Depends(require_permission("dns", "edit"))):
    try:
        rec = await cf.create_record(zone_id, data.model_dump())
    except cf.CloudflareDnsError as e:
        raise _cf_guard(e)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="dns.record.create", resource="dns",
                          resource_id=f"{data.type} {data.name}")
    return rec


@router.put("/zones/{zone_id}/records/{record_id}")
async def put_record(zone_id: str, record_id: str, data: RecordIn,
                     admin: AdminUser = Depends(require_permission("dns", "edit"))):
    try:
        rec = await cf.update_record(zone_id, record_id, data.model_dump())
    except cf.CloudflareDnsError as e:
        raise _cf_guard(e)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="dns.record.update", resource="dns",
                          resource_id=f"{data.type} {data.name}")
    return rec


@router.delete("/zones/{zone_id}/records/{record_id}")
async def del_record(zone_id: str, record_id: str,
                     admin: AdminUser = Depends(require_permission("dns", "edit"))):
    try:
        await cf.delete_record(zone_id, record_id)
    except cf.CloudflareDnsError as e:
        raise _cf_guard(e)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="dns.record.delete", resource="dns", resource_id=record_id)
    return {"deleted": True}
