"""Репутация IP — ip-api / ipinfo / IPQualityScore / AbuseIPDB.

Дополняет БС-проверку: числится ли IP в фрод/абуз-базах, помечен ли как
VPN/proxy/hosting/tor. RBAC-ресурс `reputation` (view — список/lookup,
check — управление токенами). Токены зашифрованы в bot_config.
"""
import ipaddress
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from web.backend.api.deps import AdminUser, require_permission
from web.backend.core import reputation as rep
from web.backend.core.audit import write_audit_log

logger = logging.getLogger(__name__)
router = APIRouter()


class CredsIn(BaseModel):
    token: str = Field(min_length=4, max_length=400)


class LookupIn(BaseModel):
    ip: str = Field(min_length=3, max_length=64)

    @field_validator("ip")
    @classmethod
    def _ip(cls, v: str) -> str:
        v = v.strip()
        try:
            ipaddress.ip_address(v)
        except ValueError:
            raise ValueError("некорректный IP")
        return v


@router.get("/providers")
async def list_providers(admin: AdminUser = Depends(require_permission("reputation", "view"))):
    return {"items": [
        {"slug": p.slug, "name": p.name, "needs_token": p.needs_token,
         "configured": rep.is_configured(p.slug), "signup_url": p.signup_url}
        for p in rep.providers()
    ]}


@router.put("/providers/{slug}/creds")
async def set_creds(slug: str, data: CredsIn,
                    admin: AdminUser = Depends(require_permission("reputation", "check"))):
    prov = rep.get_provider(slug)
    if not prov or not prov.needs_token:
        raise HTTPException(status_code=404, detail="Провайдер не найден или не требует токена")
    try:
        await prov.lookup("8.8.8.8", data.token.strip())   # verify токена
    except rep.RepError as e:
        raise HTTPException(status_code=400, detail=f"Токен не прошёл проверку: {e}")
    await rep.save_token(slug, data.token)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="reputation.creds.set", resource="reputation", resource_id=slug)
    return {"configured": True}


@router.delete("/providers/{slug}/creds")
async def del_creds(slug: str,
                    admin: AdminUser = Depends(require_permission("reputation", "check"))):
    await rep.clear_token(slug)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="reputation.creds.clear", resource="reputation", resource_id=slug)
    return {"configured": False}


@router.post("/lookup")
async def lookup(data: LookupIn,
                 admin: AdminUser = Depends(require_permission("reputation", "view"))):
    return {"ip": data.ip, "results": await rep.lookup_all(data.ip)}
