"""Пресеты создания юзера — именованные наборы дефолтов формы.

Хранятся у нас (user_presets), не в панели. Форма создания юзера
предзаполняется выбранным пресетом.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from web.backend.api.deps import AdminUser, require_permission

logger = logging.getLogger(__name__)
router = APIRouter()

# поля, которые пресет может нести (подмножество UserCreate, применимое как дефолт)
_ALLOWED_FIELDS = {
    "expire_days", "traffic_limit_bytes", "traffic_limit_strategy",
    "hwid_device_limit", "active_internal_squads", "tag", "description", "status",
}


def _clean(data: Dict[str, Any]) -> Dict[str, Any]:
    """Оставить только известные ключи (защита от мусора в JSONB)."""
    return {k: v for k, v in (data or {}).items() if k in _ALLOWED_FIELDS}


class PresetData(BaseModel):
    expire_days: Optional[int] = Field(default=None, ge=0, le=3650)
    traffic_limit_bytes: Optional[int] = Field(default=None, ge=0)
    traffic_limit_strategy: Optional[str] = None
    hwid_device_limit: Optional[int] = Field(default=None, ge=0, le=1000)
    active_internal_squads: Optional[List[str]] = None
    tag: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = Field(default=None, max_length=500)
    status: Optional[str] = None


class PresetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    data: PresetData = Field(default_factory=PresetData)


class PresetUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    data: Optional[PresetData] = None


@router.get("")
async def list_presets(admin: AdminUser = Depends(require_permission("users", "view"))):
    from shared.database import db_service
    return {"items": await db_service.list_user_presets()}


@router.post("")
async def create_preset(
    body: PresetCreate,
    admin: AdminUser = Depends(require_permission("users", "create")),
):
    from shared.database import db_service
    created = await db_service.create_user_preset(
        body.name.strip(),
        _clean(body.data.model_dump(exclude_none=True)),
        created_by=admin.username,
    )
    if not created:
        raise HTTPException(status_code=400, detail="Preset with this name already exists")
    return created


@router.patch("/{preset_id}")
async def update_preset(
    preset_id: int,
    body: PresetUpdate,
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    from shared.database import db_service
    data = _clean(body.data.model_dump(exclude_none=True)) if body.data is not None else None
    updated = await db_service.update_user_preset(
        preset_id, name=body.name.strip() if body.name else None, data=data,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Preset not found")
    return updated


@router.delete("/{preset_id}")
async def delete_preset(
    preset_id: int,
    admin: AdminUser = Depends(require_permission("users", "delete")),
):
    from shared.database import db_service
    if not await db_service.delete_user_preset(preset_id):
        raise HTTPException(status_code=404, detail="Preset not found")
    return {"status": "ok"}
