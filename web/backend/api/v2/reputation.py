"""Репутация IP — ip-api / ipinfo / IPQualityScore / AbuseIPDB.

Дополняет БС-проверку: числится ли IP в фрод/абуз-базах, помечен ли как
VPN/proxy/hosting/tor. RBAC-ресурс `reputation` (view — список/lookup,
check — управление токенами). Токены зашифрованы в bot_config.
"""
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")

from web.backend.api.deps import AdminUser, require_permission
from web.backend.core import reputation as rep
from web.backend.core.audit import write_audit_log

logger = logging.getLogger(__name__)
router = APIRouter()


class CredsIn(BaseModel):
    token: str = Field(min_length=4, max_length=400)


class LookupIn(BaseModel):
    target: str = Field(min_length=3, max_length=255)

    @field_validator("target")
    @classmethod
    def _target(cls, v: str) -> str:
        v = v.strip().lower()
        if rep.looks_ip(v) or _DOMAIN_RE.match(v):
            return v
        raise ValueError("нужен IP или домен")


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
    return {"target": data.target, "results": await rep.lookup_all(data.target)}
