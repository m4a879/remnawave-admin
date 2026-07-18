"""Subscription templates management — proxy to Remnawave Panel API."""
import base64
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from web.backend.api.deps import AdminUser, require_permission

logger = logging.getLogger(__name__)
router = APIRouter()


def _template_content(payload: dict) -> Optional[str]:
    """Редактируемый текст шаблона из объекта панели (для снапшота версии)."""
    if not isinstance(payload, dict):
        return None
    enc = payload.get("encodedTemplateYaml")
    if enc:
        try:
            return base64.b64decode(enc).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None
    tj = payload.get("templateJson")
    if tj is not None:
        return json.dumps(tj, ensure_ascii=False, indent=2)
    return None


async def _snapshot_template_baseline(template_uuid: str) -> None:
    """Зафиксировать исходный шаблон панели перед первым нашим сохранением."""
    from shared.database import db_service
    from shared.api_client import api_client
    if await db_service.list_config_versions("template", template_uuid, limit=1):
        return
    result = await api_client.get_template(template_uuid)
    payload = result.get("response", result) or {}
    content = _template_content(payload)
    if content:
        await db_service.save_config_version(
            "template", template_uuid, content,
            entity_name=payload.get("name"), created_by="baseline",
        )


class TemplateCreate(BaseModel):
    name: str
    templateType: str  # XRAY_JSON, XRAY_BASE64, MIHOMO, STASH, CLASH, SINGBOX


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    templateJson: Optional[dict] = None
    # YAML-шаблоны (MIHOMO/CLASH/STASH): base64-строка YAML
    encodedTemplateYaml: Optional[str] = None


class ReorderItem(BaseModel):
    uuid: str
    viewPosition: int


class ReorderRequest(BaseModel):
    items: list[ReorderItem]


@router.get("")
async def list_templates(
    admin: AdminUser = Depends(require_permission("resources", "view")),
):
    """List all subscription templates."""
    try:
        from shared.api_client import api_client
        result = await api_client.get_templates()
        payload = result.get("response", {})
        # 2.8.0 отдаёт response.templates; старые панели — subscriptionTemplates
        templates = (
            (payload.get("templates") or payload.get("subscriptionTemplates") or [])
            if isinstance(payload, dict) else []
        )
        return {"items": templates, "total": len(templates)}
    except Exception as e:
        logger.error("Failed to list templates: %s", e)
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


@router.get("/{template_uuid}")
async def get_template(
    template_uuid: str,
    admin: AdminUser = Depends(require_permission("resources", "view")),
):
    """Get a single template by UUID."""
    try:
        from shared.api_client import api_client
        result = await api_client.get_template(template_uuid)
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to get template: %s", e)
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


@router.post("")
async def create_template(
    data: TemplateCreate,
    admin: AdminUser = Depends(require_permission("resources", "create")),
):
    """Create a new subscription template."""
    try:
        from shared.api_client import api_client
        result = await api_client.create_template(data.name, data.templateType)
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to create template: %s", e)
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


@router.get("/{template_uuid}/versions")
async def list_template_versions(
    template_uuid: str,
    admin: AdminUser = Depends(require_permission("resources", "view")),
):
    """История сохранений шаблона через встроенный редактор."""
    from shared.database import db_service
    return {"items": await db_service.list_config_versions("template", template_uuid)}


@router.get("/versions/{version_id}")
async def get_template_version(
    version_id: int,
    admin: AdminUser = Depends(require_permission("resources", "view")),
):
    """Содержимое конкретной версии шаблона (для отката/диффа)."""
    from shared.database import db_service
    version = await db_service.get_config_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return version


@router.patch("/{template_uuid}")
async def update_template(
    template_uuid: str,
    data: TemplateUpdate,
    admin: AdminUser = Depends(require_permission("resources", "edit")),
):
    """Update a subscription template."""
    from shared.exceptions import ServerError, ValidationError
    # бейзлайн исходника перед первым нашим редактированием
    try:
        await _snapshot_template_baseline(template_uuid)
    except Exception as e:
        logger.warning("Baseline snapshot for template %s failed: %s", template_uuid, e)

    try:
        from shared.api_client import api_client
        result = await api_client.update_template(
            template_uuid,
            name=data.name,
            template_json=data.templateJson,
            encoded_template_yaml=data.encodedTemplateYaml,
        )
    except (ValidationError, ServerError) as e:
        # панель отклонила шаблон — доносим её текст
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to update template: %s", e)
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")

    # снапшот новой версии (дедуп по хэшу внутри)
    try:
        from shared.database import db_service
        content = _template_content({
            "templateJson": data.templateJson,
            "encodedTemplateYaml": data.encodedTemplateYaml,
        })
        if content:
            await db_service.save_config_version(
                "template", template_uuid, content, created_by=admin.username,
            )
    except Exception as e:
        logger.warning("Version snapshot for template %s failed: %s", template_uuid, e)

    return result.get("response", result)


@router.delete("/{template_uuid}")
async def delete_template(
    template_uuid: str,
    admin: AdminUser = Depends(require_permission("resources", "delete")),
):
    """Delete a subscription template."""
    try:
        from shared.api_client import api_client
        await api_client.delete_template(template_uuid)
        return {"status": "ok"}
    except Exception as e:
        logger.error("Failed to delete template: %s", e)
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


@router.post("/reorder")
async def reorder_templates(
    data: ReorderRequest,
    admin: AdminUser = Depends(require_permission("resources", "edit")),
):
    """Reorder subscription templates."""
    try:
        from shared.api_client import api_client
        items = [{"uuid": item.uuid, "viewPosition": item.viewPosition} for item in data.items]
        result = await api_client.reorder_templates(items)
        return result.get("response", {"status": "ok"})
    except Exception as e:
        logger.error("Failed to reorder templates: %s", e)
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")
