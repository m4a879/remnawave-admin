"""BS-Check API — проверка нод через операторов РФ (bschekbot/bsbord).

Показывает, проходит ли IP ноды через операторский DPI/белые списки. Проба
платная (кредиты bsbord) — перед запуском есть /probe/preview с ценой. Токен
хранится зашифрованным; RBAC-ресурс `bscheck` (view — читать/превью, check —
запускать пробу и управлять токеном).
"""
import logging
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from web.backend.api.deps import AdminUser, require_permission
from web.backend.core import bscheck as bs
from web.backend.core.audit import write_audit_log
from shared.database import db_service

logger = logging.getLogger(__name__)
router = APIRouter()


def _upstream(e: bs.BscheckError) -> HTTPException:
    return HTTPException(status_code=502, detail=str(e))


# ── Схемы ────────────────────────────────────────────────────────


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ProbeIn(BaseModel):
    target: str = Field(min_length=1, max_length=255)
    operators: List[str] = Field(default_factory=list)   # op_key[]; пусто = все
    probes: Dict[str, bool] = Field(default_factory=lambda: {"icmp": True, "tcp": True, "sni": False})
    sni_hosts: List[str] = Field(default_factory=list)
    dpi: str = "on"

    @field_validator("dpi")
    @classmethod
    def _dpi(cls, v: str) -> str:
        if v not in ("on", "any"):
            raise ValueError("dpi must be on|any")
        return v


def _body(p: ProbeIn) -> Dict:
    return {"target": p.target.strip(), "operators": p.operators,
            "probes": p.probes, "sni_hosts": p.sni_hosts, "dpi": p.dpi}


# ── Токен / статус ───────────────────────────────────────────────


@router.get("/status")
async def status(admin: AdminUser = Depends(require_permission("bscheck", "view"))):
    if not bs.is_configured():
        return {"configured": False, "account": None}
    account = None
    try:
        account = await bs.get_account()
    except bs.BscheckError as e:
        logger.info("bscheck account: %s", e)
    return {"configured": True, "account": account}


@router.put("/token")
async def set_token(data: TokenIn,
                    admin: AdminUser = Depends(require_permission("bscheck", "check"))):
    if not await bs.verify_token(data.token.strip()):
        raise HTTPException(status_code=400, detail="Токен недействителен или тариф ниже Bronze")
    await bs.save_token(data.token)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="bscheck.token.set", resource="bscheck", resource_id="token")
    return {"configured": True}


@router.delete("/token")
async def clear_token(admin: AdminUser = Depends(require_permission("bscheck", "check"))):
    await bs.clear_token()
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="bscheck.token.clear", resource="bscheck", resource_id="token")
    return {"configured": False}


# ── Операторы / превью / проверка ────────────────────────────────


@router.get("/operators")
async def operators(admin: AdminUser = Depends(require_permission("bscheck", "view"))):
    try:
        return {"items": await bs.get_operators()}
    except bs.BscheckError as e:
        raise _upstream(e)


@router.post("/probe/preview")
async def preview(data: ProbeIn, admin: AdminUser = Depends(require_permission("bscheck", "view"))):
    try:
        return await bs.probe_preview(_body(data))
    except bs.BscheckError as e:
        raise _upstream(e)


@router.post("/nodes/{node_uuid}/check")
async def check_node(node_uuid: str, data: ProbeIn,
                     admin: AdminUser = Depends(require_permission("bscheck", "check"))):
    try:
        result = await bs.probe(_body(data))
    except bs.BscheckError as e:
        raise _upstream(e)
    summary = bs.summarize(result, data.target.strip())
    saved = await db_service.save_bscheck(
        node_uuid, summary["passed"], summary["total"], summary.get("cost_credits"),
        {"summary": summary, "raw": result}, created_by=admin.username)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="bscheck.node.check", resource="bscheck", resource_id=node_uuid)
    return {"summary": summary, "checked_at": saved.get("checked_at") if saved else None}


@router.get("/nodes/{node_uuid}")
async def node_history(node_uuid: str,
                       admin: AdminUser = Depends(require_permission("bscheck", "view"))):
    return {
        "last": await db_service.get_last_bscheck(node_uuid),
        "history": await db_service.list_bscheck(node_uuid, 20),
    }


@router.get("/summary")
async def summary_map(admin: AdminUser = Depends(require_permission("bscheck", "view"))):
    return {"items": await db_service.get_bscheck_summary_map()}
